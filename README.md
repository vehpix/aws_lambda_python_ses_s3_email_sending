# AWS Lambda - Python / SES / S3 / Emailing Forwarding
Example Python Script written for AWS Lambda to process SES emails forwarded to an S3 bucket

Still need to update permissios and provide context of problem and solution this fixes.



General:

Enable SES to forward emails from your domain to S3.  S3 triggers the lambda function which extracts the core info from the S3 file including attachments and forwards, using your noreply@vehpix.com to your email account (gmail, hotmail, outlook, etc. )