from django.db import models
from django.utils import crypto

from oauth_pen.settings import oauth_pen_settings
from . import generators


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

    class Meta:
        abstract = True


class Application(ApplicationAbstract):
    """
    客户端信息
    """
    pass


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
