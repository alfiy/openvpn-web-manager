import smtplib
from email.mime.text import MIMEText

# 正确写法：服务器域名 + 端口
smtp = smtplib.SMTP_SSL('smtp.qq.com', 465)
smtp.login('13012648@qq.com', 'czdvjiwiiektbiah')

msg = MIMEText('这是一条测试正文')
msg['Subject'] = '测试邮件'
msg['From'] = '13012648@qq.com'
msg['To'] = '13012648@qq.com'

smtp.sendmail('13012648@qq.com', ['13012648@qq.com'], msg.as_string())
smtp.quit()
print('发送成功')
