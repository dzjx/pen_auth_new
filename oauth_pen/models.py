from urllib.parse import urlparse, parse_qsl

from django.apps import apps
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import crypto, timezone
from django.contrib.auth import hashers

from oauth_pen.exceptions import ErrorConfigException
from oauth_pen.settings import oauth_pen_settings
from oauth_pen import generators


class ApplicationAbstract(models.Model):
    """
    客户端信息抽象类
    """

    # 客户端类型
    CLIENT_CONFIDENTIAL = 'confidential'
    CLIENT_PUBLIC = 'public'
    CLIENT_TYPES = (
        (CLIENT_CONFIDENTIAL, '私有'),
        (CLIENT_PUBLIC, '公用'),
    )

    # 授权类型
    GRANT_AUTHORIZATION_CODE = 'authorization-code'
    GRANT_IMPLICIT = 'implicit'
    GRANT_PASSWORD = 'password'
    GRANT_CLIENT_CREDENTIALS = 'client-credentials'
    GRANT_TYPES = (
        (GRANT_AUTHORIZATION_CODE, '授权码'),
        (GRANT_IMPLICIT, '简化'),
        (GRANT_PASSWORD, '密码'),
        (GRANT_CLIENT_CREDENTIALS, '客户端'),
    )
    client_name = models.CharField('客户端名称', max_length=255, default='')
    client_id = models.CharField('客户端唯一标识', max_length=100, primary_key=True,
                                 default=generators.ClientIDGenerator().hash())
    client_secret = models.CharField('客户端密钥', max_length=255, default=generators.ClientSecretGenerator().hash())
    client_type = models.CharField('客户端类型', max_length=20, choices=CLIENT_TYPES, default=CLIENT_CONFIDENTIAL)
    authorization_grant_type = models.CharField('授权类型', max_length=50, choices=GRANT_TYPES, default=GRANT_PASSWORD)
    user_id = models.CharField('创建人ID', max_length=20, default=0, db_index=True)
    skip_authorization = models.BooleanField('TODO 是否跳过授权', default=False)
    redirect_uris = models.TextField('TODO 授权成功回调地址（implicit/authorization-code 模式必填写）', blank=True)
    remark = models.TextField('客户端说明', blank=True, default='')

    def __str__(self):
        return self.client_name + ':' + self.client_id

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.redirect_uris \
                and self.authorization_grant_type in (self.GRANT_IMPLICIT, self.GRANT_CLIENT_CREDENTIALS):
            raise ValidationError('{0}模式下必填写redirect_uris'.format(self.authorization_grant_type))

    def is_usable(self, request):
        """
        客户端是否可使用
        :param request: 当前请求
        :return:
        """
        return True

    def allow_grant_type(self, grant_type):
        """
        验证grant_type 是否有效
        :param grant_type:
        :return:
        """
        if grant_type == 'refresh_token':
            if self.authorization_grant_type in (
                    self.GRANT_AUTHORIZATION_CODE, self.GRANT_PASSWORD, self.GRANT_CLIENT_CREDENTIALS):
                return True
            else:
                return False
        elif self.authorization_grant_type == grant_type:
            return True
        else:
            return False

    @property
    def default_redirect_uri(self):
        if self.redirect_uris:
            return self.redirect_uris.split().pop(0)
        else:
            raise ValueError('implicit、authorization_code 模式必须设置回调地址')

    class Meta:
        abstract = True


class UserAbstract(models.Model):
    """
    用户抽象类
    """

    @property
    def is_anonymous(self):
        return False

    @property
    def is_authenticated(self):
        return True

    @property
    def is_super(self):
        return False

    def check_password(self, password):
        """
        检测密码是否正确
        :param password:用户输入的密码
        :return:
        """
        hashers.check_password(password, self.password)

    def set_password(self, password):
        """
        密码编码
        :param password:用户输入的密码
        :return:
        """
        self.password = hashers.make_password(password, __name__ + settings.SECRET_KEY)
        self._password = password

    class Meta:
        abstract = True


class Application(ApplicationAbstract):
    """
    客户端信息
    """

    def is_usable(self, request):
        """
        客户端是否可使用
        :param request: 当前请求
        :return:
        """
        # 可以控制哪些客户端可以使用，这里为了简便就都可以使用
        return True


class AccessToken(models.Model):
    user = models.ForeignKey(oauth_pen_settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    application = models.ForeignKey(oauth_pen_settings.APPLICATION_MODEL, on_delete=models.CASCADE)
    token = models.CharField(max_length=255, unique=True)
    expires = models.DateTimeField('')

    def is_expired(self):
        """
        当前token 是否过期
        :return:
        """
        if self.expires:
            return timezone.now() >= self.expires
        return True

    def is_valid(self):
        """
        当前token 是否有效
        :return:
        """

        return not self.is_expired()

    def revoke(self):
        """
        销毁一个token
        """
        self.delete()

    def __str__(self):
        return self.token


class RefreshToken(models.Model):
    """
    刷新token
    """
    access_token = models.OneToOneField(AccessToken, related_name='refresh_token', on_delete=models.CASCADE)
    user = models.ForeignKey(oauth_pen_settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.CharField(max_length=255, unique=True)
    application = models.ForeignKey(oauth_pen_settings.APPLICATION_MODEL, on_delete=models.CASCADE)

    def revoke(self):
        """
        删除刷新token以及对应的token
        """
        AccessToken.objects.get(id=self.access_token.id).revoke()
        self.delete()

    def __str__(self):
        return self.token


class Grant(models.Model):
    """
    一个短时间的临时凭证，用于交换token
    """
    user = models.ForeignKey(oauth_pen_settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField('用于换取token的code', max_length=255, unique=True)
    application = models.ForeignKey(oauth_pen_settings.APPLICATION_MODEL, on_delete=models.CASCADE)
    expires = models.DateTimeField('code有效期')
    redirect_uris = models.CharField('换取token后的回调地址(多个回调地址空格分开)', max_length=255)
    state = models.TextField('客户端数据', blank=True)

    def is_expired(self):
        """
        检查code 是否过期
        """
        if not self.expires:
            return True

        return timezone.now() >= self.expires

    def redirect_uri_allowed(self, uri):
        """
        回调地址是否有效
        :param uri:
        :return:
        """
        for allowed_uri in self.redirect_uris.split():
            parsed_allowed_uri = urlparse(allowed_uri)
            parsed_uri = urlparse(uri)
            if parsed_allowed_uri.scheme == parsed_uri.scheme and parsed_allowed_uri.netloc == parsed_uri.netloc and parsed_allowed_uri.path == parsed_uri.path:
                aqs_set = set(parse_qsl(parsed_allowed_uri.query))
                uqs_set = set(parse_qsl(parsed_uri.query))

                if aqs_set.issubset(uqs_set):
                    return True

        return False


class User(UserAbstract):
    username = models.CharField('用户名', max_length=255, unique=True)
    password = models.CharField('密码', max_length=255)
    is_active = models.BooleanField('是否激活', default=True)


class AnonymousUser(UserAbstract):
    """
    匿名用户
    """

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        raise NotImplementedError('AnonymousUser 不提供保存')

    def delete(self, using=None, keep_parents=False):
        raise NotImplementedError('AnonymousUser 不提供删除')

    @property
    def is_anonymous(self):
        return True

    @property
    def is_authenticated(self):
        return False


class SuperUser(UserAbstract):
    """
    平台管理员
    """

    # 通过配置文件配置管理员帐号
    user_id = '1'
    username = oauth_pen_settings.ADMIN_NAME
    password = oauth_pen_settings.ADMIN_PASSWORD

    def get_session_auth_hash(self):
        """
        获取用户密码的hmac hash值
        :return:
        """
        key_salt = 'oauth_pen.models' + self.__class__.__name__

        # 在对value计算 hamc hash值时 最好每一个密钥都不一样，所以这里的key_salt传的是当前的方法路径，将key_salt和setting.SECRET_KEY 组合起来作为密钥计算hmac 的hash值
        return crypto.salted_hmac(key_salt, self.password).hexdigest()

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        raise NotImplementedError('SuperUser 不提供保存')

    def delete(self, using=None, keep_parents=False):
        raise NotImplementedError('SuperUser 不提供删除')

    @property
    def is_anonymous(self):
        return False

    @property
    def is_authenticated(self):
        return True

    @property
    def is_super(self):
        return True

    @property
    def logout_path(self):
        return reverse('pen_admin:logout')


def get_application_model():
    """
    获取客户端实例
    :return:
    """
    try:
        app_label, model_name = oauth_pen_settings.APPLICATION_MODEL.split('.')
    except ValueError:
        raise ErrorConfigException('APPLICATION_MODEL 配置错误 eg: oauth_pen.models.Application')
    app_model = apps.get_model(app_label, model_name)
    if app_model is None:
        raise ErrorConfigException('{0} 不存在'.format(oauth_pen_settings.APPLICATION_MODEL))
    return app_model


def get_user_model():
    """
    获取用户实例
    :return:
    """
    try:
        app_label, model_name = oauth_pen_settings.AUTH_USER_MODEL.split('.')
    except ValueError:
        raise ErrorConfigException('APPLICATION_MODEL 配置错误 eg: oauth_pen.models.User')
    app_model = apps.get_model(app_label, model_name)
    if app_model is None:
        raise ErrorConfigException('{0} 不存在'.format(oauth_pen_settings.AUTH_USER_MODEL))
    return app_model
