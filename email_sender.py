# email_sender.py
"""
Email sending functionality with SMTP configuration and attachment support.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger("email-sender")


class EmailSender:
    """
    Email sender with SMTP support and attachment capabilities.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        use_tls: bool = True,
        use_ssl: bool = False,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.use_tls = use_tls
        self.use_ssl = use_ssl
        self.from_email = from_email or smtp_user
        self.from_name = from_name or "看小說 Admin"

    def send_email(
        self,
        to_email: str | List[str],
        subject: str,
        body: str,
        is_html: bool = False,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[str | Path]] = None,
    ) -> Dict[str, Any]:
        """
        Send an email with optional attachments.

        Args:
            to_email: Recipient email address(es)
            subject: Email subject
            body: Email body (plain text or HTML)
            is_html: Whether body is HTML (default: False)
            cc: CC recipients
            bcc: BCC recipients
            attachments: List of file paths to attach

        Returns:
            Dict with status and message
        """
        try:
            # Convert single recipient to list
            if isinstance(to_email, str):
                to_email = [to_email]

            # Create message
            msg = MIMEMultipart()
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = ", ".join(to_email)
            msg['Subject'] = subject

            if cc:
                msg['Cc'] = ", ".join(cc)
            if bcc:
                msg['Bcc'] = ", ".join(bcc)

            # Attach body
            mime_type = 'html' if is_html else 'plain'
            msg.attach(MIMEText(body, mime_type, 'utf-8'))

            # Attach files
            if attachments:
                for attachment_path in attachments:
                    try:
                        file_path = Path(attachment_path)
                        if not file_path.exists():
                            logger.warning(f"[EmailSender] Attachment not found: {file_path}")
                            continue

                        with open(file_path, 'rb') as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                'Content-Disposition',
                                f'attachment; filename={file_path.name}'
                            )
                            msg.attach(part)
                            logger.debug(f"[EmailSender] Attached file: {file_path.name}")
                    except Exception as e:
                        logger.error(f"[EmailSender] Failed to attach file {attachment_path}: {e}")

            # Collect all recipients
            all_recipients = to_email + (cc or []) + (bcc or [])

            # Send email
            if self.use_ssl:
                # Use SMTP_SSL for implicit SSL
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.from_email, all_recipients, msg.as_string())
            else:
                # Use SMTP with optional STARTTLS
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.from_email, all_recipients, msg.as_string())

            logger.info(f"[EmailSender] Email sent successfully to {', '.join(to_email)}")
            return {
                "status": "success",
                "message": f"Email sent to {', '.join(to_email)}",
                "recipients": len(all_recipients)
            }

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"[EmailSender] SMTP authentication failed: {e}")
            return {
                "status": "error",
                "message": "SMTP authentication failed. Check username and password.",
                "error": str(e)
            }
        except smtplib.SMTPException as e:
            logger.error(f"[EmailSender] SMTP error: {e}")
            return {
                "status": "error",
                "message": f"SMTP error: {str(e)}",
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"[EmailSender] Failed to send email: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "message": f"Failed to send email: {str(e)}",
                "error": str(e)
            }

    def test_connection(self) -> Dict[str, Any]:
        """
        Test SMTP connection and authentication.

        Returns:
            Dict with status and message
        """
        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10) as server:
                    server.login(self.smtp_user, self.smtp_password)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.smtp_user, self.smtp_password)

            logger.info("[EmailSender] SMTP connection test successful")
            return {
                "status": "success",
                "message": "SMTP connection successful"
            }
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"[EmailSender] SMTP authentication failed: {e}")
            return {
                "status": "error",
                "message": "SMTP authentication failed. Check username and password.",
                "error": str(e)
            }
        except smtplib.SMTPException as e:
            logger.error(f"[EmailSender] SMTP error: {e}")
            return {
                "status": "error",
                "message": f"SMTP error: {str(e)}",
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"[EmailSender] Connection test failed: {e}")
            return {
                "status": "error",
                "message": f"Connection failed: {str(e)}",
                "error": str(e)
            }


# Global email sender instance
email_sender: Optional[EmailSender] = None


def init_email_sender(smtp_config: Dict[str, Any]) -> EmailSender:
    """Initialize the global email sender with configuration."""
    global email_sender
    email_sender = EmailSender(
        smtp_host=smtp_config.get('smtp_host', ''),
        smtp_port=smtp_config.get('smtp_port', 587),
        smtp_user=smtp_config.get('smtp_user', ''),
        smtp_password=smtp_config.get('smtp_password', ''),
        use_tls=smtp_config.get('use_tls', True),
        use_ssl=smtp_config.get('use_ssl', False),
        from_email=smtp_config.get('from_email'),
        from_name=smtp_config.get('from_name', '看小說 Admin'),
    )
    return email_sender
