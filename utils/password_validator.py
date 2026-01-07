# utils/password_validator.py
import re
from typing import Tuple

class PasswordValidator:
    """统一的密码验证工具"""
    
    # 密码强度正则：至少8位最大20位，包含大小写字母、数字和特殊字符
    PASSWORD_PATTERN = re.compile(
        r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9])[^\s]{8,20}$'
    )
    
    ERROR_MESSAGES = {
        'too_short': '密码至少需要8个字符,最多20个字符',
        'weak': '密码需包含大小写字母、数字和特殊字符',
        'mismatch': '两次输入的密码不一致',
        'empty': '密码不能为空'
    }
    
    @classmethod
    def validate_strength(cls, password: str) -> Tuple[bool, str]:
        """
        验证密码强度
        
        Args:
            password: 待验证的密码
            
        Returns:
            (是否有效, 错误消息)
        """
        if not password:
            return False, cls.ERROR_MESSAGES['empty']
        
        if len(password) < 8:
            return False, cls.ERROR_MESSAGES['too_short']
        
        if not cls.PASSWORD_PATTERN.match(password):
            return False, cls.ERROR_MESSAGES['weak']
        
        return True, ''
    
    @classmethod
    def validate_match(cls, password: str, confirm_password: str) -> Tuple[bool, str]:
        """
        验证两次密码是否一致
        
        Args:
            password: 密码
            confirm_password: 确认密码
            
        Returns:
            (是否匹配, 错误消息)
        """
        if password != confirm_password:
            return False, cls.ERROR_MESSAGES['mismatch']
        
        return True, ''
    
    @classmethod
    def validate_full(cls, password: str, confirm_password: str) -> Tuple[bool, str]:
        """
        完整验证：强度 + 一致性
        
        Args:
            password: 密码
            confirm_password: 确认密码
            
        Returns:
            (是否有效, 错误消息)
        """
        # 先验证强度
        valid, msg = cls.validate_strength(password)
        if not valid:
            return False, msg
        
        # 再验证一致性
        valid, msg = cls.validate_match(password, confirm_password)
        if not valid:
            return False, msg
        
        return True, ''