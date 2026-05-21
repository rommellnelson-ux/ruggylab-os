from passlib.context import CryptContext
pwd= 'SuperAdmin2026!SecurePass'
hash='$pbkdf2-sha256$29000$670XorSWUgpBaA1BaM15Lw$l/2lDdS/TeszlFvoGIKZMqgQiDg3Cys647kDaDK65NI'
ctx=CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')
print('verify:', ctx.verify(pwd, hash))
