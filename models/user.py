from flask_login import UserMixin
from datetime import datetime

class User(UserMixin):
    def __init__(self, _id=None, username='', email='', password='', role='student', created_at=None):
        self._id = _id
        self.username = username
        self.email = email
        self.password = password  # Без хеширования для упрощения
        self.role = role  # 'admin', 'teacher', 'student'
        self.created_at = created_at or datetime.utcnow()
    
    def get_id(self):
        return str(self._id)
    
    @staticmethod
    def from_db_document(user_doc):
        if not user_doc:
            return None
        return User(
            _id=user_doc.get('_id'),
            username=user_doc.get('username'),
            email=user_doc.get('email'),
            password=user_doc.get('password'),
            role=user_doc.get('role', 'student'),
            created_at=user_doc.get('created_at')
        )
    
    def to_db_document(self):
        return {
            'username': self.username,
            'email': self.email,
            'password': self.password,
            'role': self.role,
            'created_at': self.created_at
        }
    
    def is_admin(self):
        return self.role == 'admin'
    
    def is_teacher(self):
        return self.role == 'teacher'
    
    def is_student(self):
        return self.role == 'student'