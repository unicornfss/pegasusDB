import os
import logging
from telegram import Bot
from telegram.error import TelegramError
from django.conf import settings
from ..models import Personnel, TelegramNotification

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        self.bot = Bot(token=self.bot_token) if self.bot_token else None

    def is_configured(self):
        """Check if Telegram bot is properly configured"""
        return self.bot is not None

    def send_notification(self, instructor, booking, message_text, sent_by=None, notification_type="admin_send"):
        """
        Send a Telegram notification to an instructor for a booking.

        Args:
            instructor: Personnel instance
            booking: Booking instance
            message_text: The message to send
            sent_by: User who sent the notification (optional)
            notification_type: Type of notification

        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.is_configured():
            logger.warning("Telegram bot not configured")
            return False

        if not instructor.telegram_chat_id:
            logger.info(f"No Telegram chat ID for instructor {instructor.name}")
            return False

        try:
            # Send the message
            message = self.bot.send_message(
                chat_id=instructor.telegram_chat_id,
                text=message_text,
                parse_mode='HTML'
            )

            # Record the notification in database
            TelegramNotification.objects.create(
                booking=booking,
                instructor=instructor,
                sent_at=message.date,
                sent_by=sent_by,
                message_text=message_text,
                telegram_message_id=str(message.message_id),
                notification_type=notification_type
            )

            logger.info(f"Telegram notification sent to {instructor.name} for booking {booking.course_reference}")
            return True

        except TelegramError as e:
            logger.error(f"Failed to send Telegram notification to {instructor.name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram notification: {e}")
            return False

    def send_course_notification(self, booking, sent_by=None, notification_type="admin_send"):
        """
        Send a notification about a course to the assigned instructor.

        Args:
            booking: Booking instance
            sent_by: User who sent the notification (optional)
            notification_type: Type of notification

        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not booking.instructor:
            logger.info(f"No instructor assigned to booking {booking.course_reference}")
            return False

        instructor = booking.instructor

        # Create the message
        message_text = f"""
🔔 <b>Course Notification</b>

<b>Course:</b> {booking.course_type.name}
<b>Reference:</b> {booking.course_reference}
<b>Date:</b> {booking.course_date.strftime('%A, %d %B %Y')}
<b>Location:</b> {booking.training_location.name}, {booking.training_location.business.name}
<b>Business:</b> {booking.business.name}

<b>Status:</b> {booking.get_status_display()}

Please check the system for more details.
        """.strip()

        return self.send_notification(
            instructor=instructor,
            booking=booking,
            message_text=message_text,
            sent_by=sent_by,
            notification_type=notification_type
        )

# Global service instance
telegram_service = TelegramService()