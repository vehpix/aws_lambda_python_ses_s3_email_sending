import base64
import boto3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import json
import os

def lambda_handler(event, context):
    for record in event.get('Records',[]):
        if record.get('eventSource','') == 'aws:s3':
            file_content = get_file_from_s3(record['s3']['bucket']['name'], record['s3']['object']['key'])
            details = get_details_from_email(file_content)
            response_code, response = forward_email(details)
            
            if response_code == 200:
                return {
                    'statusCode': 200,
                    'body': json.dumps('Email forwarded successfully')
                }
            else:
                print("Failed to forward email:", response)
                return {
                    'statusCode': response_code,
                    'body': json.dumps('Failed to forward email')
                }


def forward_email(details):

    from_val = os.environ.get('sesNoReplyEmailAddr',"noreply@missing.com")
    to_val = os.environ.get('sesForwardEmailAddr','target@missing.com')
    orig_to_name = details['to_email'].split('@')[0].replace('.',' ').title()

    msg = MIMEMultipart()
    # Set From to the verified SES sender
    msg['From'] = from_val
    msg['To'] = to_val
    msg['Subject'] = f"VehPix Email To {orig_to_name}: {details['subject']}"
    msg['Date'] = details['date']
    # Set Reply-To to the original sender
    msg.add_header('Reply-To', f"{details['from_name']} <{details['from_email']}>")

    # Attach the body
    body = (
        f"From: {details['from_name']} <{details['from_email']}>\n"
        f"To: {details['to_name']} <{details['to_email']}>\n"
        f"Subject: {details['subject']}\n"
        f"Date: {details['date']}\n\n"
        f"{details['body']}"
    )

    msg.attach(MIMEText(body, 'plain'))

    # Attach files if any
    for attachment in details.get('attachments', []):
        if attachment.get('content'):
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(base64.b64decode(attachment['content']))
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{attachment['name']}"')
            if attachment.get('type'):
                part.add_header('Content-Type', attachment['type'])
            msg.attach(part)

    ses = boto3.client("ses")
    response = ses.send_raw_email(
        Source=from_val,
        Destinations=[to_val],
        RawMessage={
            'Data': msg.as_string()
        }
    )
    response_code = response['ResponseMetadata']['HTTPStatusCode']
    return response_code, response

# This function extracts details from the email content
def get_details_from_email(file_content):

    email_details = {
        "from_email" : "",
        "from_name" : "",
        "to_email" : "",
        "to_name" : "",
        "subject" : "",
        "date" : "",
        "body" : "",
        "attachment": False,
        "attachments": []
    }

    blank_attachment = {
        "type":"",
        "name":"",
        "content":"",
        "identified":False
    }
    current_attachment = {}

    contentRow = None
    message_body_row_start = None
    message_body_in_progress = False
    message_body_content = ""

    attachment_body_row_start = None
    attachment_body_in_progress = False
    for index, row in enumerate(file_content.split('\n')):

        # Code to get main message body
        if message_body_in_progress:
            #print("Body extract", index, row)
            if row.strip() == '' :
                message_body_in_progress = False
                continue
            message_body_content += row
            continue
        elif message_body_row_start != None and index == message_body_row_start:
            message_body_in_progress = True
            message_body_content = row
            if row == '':
                message_body_in_progress = False
                message_body_row_start = None
            continue
        
        # Attachment
        elif attachment_body_in_progress == True:
            if row.strip() == '' :
                attachment_body_in_progress = False
                email_details['attachments'].append(current_attachment)
                current_attachment = json.loads(json.dumps({}))
                continue
            current_attachment['content'] += row
            continue
        elif attachment_body_row_start != None and index == attachment_body_row_start:
            attachment_body_in_progress = True
            current_attachment['content'] = row
            if row.strip() == '' :
                attachment_body_in_progress = False
                email_details['attachments'].append(current_attachment)
                current_attachment = json.loads(json.dumps({}))
                continue
        elif current_attachment.get('identified',False) == True:
            if 'Content-Transfer-Encoding' in row:
                attachment_body_row_start = index + 2
                continue
        # Main core info iteration
        elif row.startswith('From:'):
            email_details['from_email'] = row.split('<')[1].split('>')[0]
            email_details['from_name'] = row.split('From:')[1].split('<')[0].strip().replace('"','')
            continue
        elif row.startswith('Subject:'):
            email_details['subject'] = row.split('Subject:')[1].strip()
            continue
        elif row.startswith('Date:'):
            email_details['date'] = row.split('Date:')[1].strip()
            continue
        elif row.startswith('To:'):
            email_details['to_email'] = row.split('<')[1].split('>')[0]
            email_details['to_name'] = row.split('To:')[1].split('<')[0].strip().replace('"','')
            continue
        elif row.startswith('X-MS-Has-Attach'):
            if 'yes' in row:
                email_details['attachment'] = True
            continue
        elif row.startswith('Content-Type'):
            if 'text/plain' in row and 'charset' in row:
                email_details['body'] = row.split('Content-Type: text/plain')[1].strip()
                message_body_row_start = index + 3
                continue
            elif 'multipart' in row:
                pass
            elif 'text/html' in row:
                pass
            else:
                current_attachment = json.loads(json.dumps(blank_attachment))
                current_attachment['type'] = row.split('Content-Type: ')[1].split(';')[0]
                current_attachment['name'] = row.split('name="')[1].split('"')[0]
                current_attachment['identified'] = True
                continue

    try:
        email_details['body'] = base64.b64decode(message_body_content).decode()
    except:
        email_details['body'] = message_body_content

    return email_details


def get_file_from_s3(s3_bucket, s3_key):
    s3 = boto3.client('s3')
    response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    return response['Body'].read().decode('utf-8')