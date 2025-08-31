
"""
Monthly Competition Telegram Bot

Setup Instructions:
1. Install required packages:
   pip install python-telegram-bot sqlite3

2. Create a bot with @BotFather on Telegram and get your bot token

3. Replace "YOUR_BOT_TOKEN_HERE" with your actual bot token

4. Run the script:
   python competition_bot.py

5. Add the bot to your Telegram group - the person who adds it becomes the first admin

6. Create your first challenge using /startchallenge in a private message to the bot

Features:
- User registration with custom usernames
- Point tracking with date ranges (single days or periods)
- Weekly and monthly leaderboards
- Admin system for challenge management
- Challenge voting system
- Complete CRUD operations for scores
- Confirmation workflows for all critical operations
- SQLite database for data persistence

Note: This is a foundational implementation. You may want to add additional features like:
- Challenge end dates and automatic archiving
- More sophisticated admin controls
- Data export functionality
- Enhanced error handling and logging
"""

import sqlite3
import logging
from datetime import datetime, timedelta, time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes
import re

def escape_markdown_v2(text):
    """Escape special characters for MarkdownV2"""
    if not text:
        return text
    # Characters that need escaping: _*[]()~`>#+-=|{}.!
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress verbose HTTP request logs
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram.ext.Application').setLevel(logging.WARNING)

# Conversation states
ADD_SCORE_DATE, ADD_SCORE_POINTS, ADD_SCORE_CONFIRM = range(3)
REMOVE_SCORE_DATE, REMOVE_SCORE_CONFIRM = range(2)
EDIT_SCORE_DATE, EDIT_SCORE_NEW_POINTS, EDIT_SCORE_CONFIRM = range(3)
REGISTER_USERNAME = range(1)
START_CHALLENGE_DESC, START_CHALLENGE_TYPE, START_CHALLENGE_SCORING, START_CHALLENGE_PERIOD, START_CHALLENGE_CONFIRM = range(5)
ADD_ADMIN_USERNAME, ADD_ADMIN_CONFIRM = range(2)
REMOVE_ADMIN_USERNAME, REMOVE_ADMIN_CONFIRM = range(2)
REMOVE_ENTRY_USERNAME, REMOVE_ENTRY_CONFIRM = range(2)
NEW_CHALLENGE_DESC, NEW_CHALLENGE_SCORING, NEW_CHALLENGE_CONFIRM = range(3)
BASELINE_VALUE = range(1)
UPDATE_VALUE = range(1)
EDIT_CHALLENGE_SELECT, EDIT_CHALLENGE_FIELD, EDIT_CHALLENGE_VALUE, EDIT_CHALLENGE_CONFIRM = range(4)
REMOVE_CHALLENGE_SELECT, REMOVE_CHALLENGE_CONFIRM = range(2)
FEEDBACK_VIEWING = range(1)

class CompetitionBot:
    def __init__(self, token):
        self.token = token
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect('competition_bot.db')
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                registered_username TEXT UNIQUE,
                registration_date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Scores table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date DATE,
                points INTEGER,
                challenge_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')
        
        # Challenges table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT,
                scoring_system TEXT,
                challenge_type TEXT DEFAULT 'points',
                type_description TEXT,
                start_date DATE,
                end_date DATE,
                status TEXT DEFAULT 'active',
                created_by INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add missing columns to challenges table if they don't exist
        try:
            cursor.execute("ALTER TABLE challenges ADD COLUMN challenge_type TEXT DEFAULT 'points'")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute("ALTER TABLE challenges ADD COLUMN type_description TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute("ALTER TABLE challenges ADD COLUMN created_by INTEGER")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cursor.execute("ALTER TABLE challenges ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Admins table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')
        
        # Challenge suggestions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS challenge_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                suggested_by INTEGER,
                description TEXT,
                scoring_system TEXT,
                votes INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Votes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                user_id INTEGER,
                suggestion_id INTEGER,
                PRIMARY KEY (user_id, suggestion_id)
            )
        ''')
        
        # Challenge notifications table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS challenge_notifications (
                challenge_id INTEGER,
                notification_type TEXT,
                sent_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (challenge_id, notification_type)
            )
        ''')
        
        # Baseline values table for change challenges
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS baseline_values (
                user_id INTEGER,
                challenge_id INTEGER,
                baseline_value REAL,
                current_value REAL,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, challenge_id),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                FOREIGN KEY (challenge_id) REFERENCES challenges(id)
            )
        ''')
        
        # Feedback table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                feedback_text TEXT,
                submitted_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')
        
        conn.commit()
        conn.close()

    def get_db_connection(self):
        """Get database connection"""
        return sqlite3.connect('competition_bot.db')

    def is_admin(self, user_id):
        """Check if user is admin"""
        # Check if user is lucaspuu (fixed admin)
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT username FROM users WHERE telegram_id = ?', (user_id,))
        user_result = cursor.fetchone()
        if user_result and user_result[0] == 'lucaspuu':
            conn.close()
            return True
        
        # Check regular admin status
        cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
        result = cursor.fetchone() is not None
        conn.close()
        return result

    def get_current_challenge(self):
        """Get current active challenge (including upcoming and grace period)"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM challenges WHERE status IN ("active", "upcoming", "grace_period") ORDER BY created_at DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        return result
    
    def get_challenge_status(self, challenge):
        """Determine the actual status of a challenge based on current date"""
        if not challenge:
            return None, None
        
        # Handle different database schema versions
        if len(challenge) == 8:
            # 8-column version (missing challenge_type and type_description)
            challenge_id, description, scoring_system, start_date, end_date, status, created_by, created_at = challenge
        else:
            # 10-column version - actual order from database after migration
            challenge_id, description, scoring_system, start_date, end_date, status, created_by, created_at, challenge_type, type_description = challenge
        now = datetime.now()
        start_datetime = datetime.strptime(str(start_date), '%Y-%m-%d')
        end_datetime = datetime.strptime(str(end_date), '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1)  # End at 23:59:59
        grace_end = end_datetime + timedelta(days=1)
        
        def format_time_remaining(time_diff):
            """Format time difference into human-readable string"""
            print(time_diff)
            if time_diff.days > 1:
                return f"{time_diff.days} days"
            elif time_diff.days == 1:
                return "1 day"
            else:
                hours = time_diff.seconds // 3600
                
                minutes = (time_diff.seconds % 3600) // 60
                
                if hours > 0:
                    return f"{hours} hour{'s' if hours != 1 else ''}"
                elif minutes > 0:
                    return f"{minutes} minute{'s' if minutes != 1 else ''}"
                else:
                    return "less than a minute"
        
        if now < start_datetime:
            time_until = start_datetime - now
            time_str = format_time_remaining(time_until)
            return "upcoming", f"Starts in {time_str}"
        elif start_datetime <= now <= end_datetime:
            time_left = end_datetime - now
            time_str = format_time_remaining(time_left)
            return "active", f"Active \\- {time_str} remaining\\!"
        elif end_datetime < now <= grace_end:
            time_left = grace_end - now
            time_str = format_time_remaining(time_left)
            return "grace_period", f"Grace period \\- {time_str} left to submit\\!"
        else:
            return "ended", "Challenge has ended"
    
    def update_challenge_status(self, challenge_id, new_status):
        """Update challenge status in database"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE challenges SET status = ? WHERE id = ?', (new_status, challenge_id))
        conn.commit()
        conn.close()
    
    def has_notification_been_sent(self, challenge_id, notification_type):
        """Check if a notification has already been sent"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1 FROM challenge_notifications 
            WHERE challenge_id = ? AND notification_type = ?
        ''', (challenge_id, notification_type))
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    def mark_notification_sent(self, challenge_id, notification_type):
        """Mark a notification as sent"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO challenge_notifications (challenge_id, notification_type)
            VALUES (?, ?)
        ''', (challenge_id, notification_type))
        conn.commit()
        conn.close()
    
    def get_challenge_stats(self, challenge_id):
        """Calculate interesting stats for the challenge"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Get challenge date range
        cursor.execute('SELECT start_date, end_date FROM challenges WHERE id = ?', (challenge_id,))
        challenge_dates = cursor.fetchone()
        if not challenge_dates:
            conn.close()
            return stats
        
        start_date, end_date = challenge_dates
        
        # Average points per active player (excluding 0-point players)
        cursor.execute('''
            SELECT AVG(total_points) as avg_points
            FROM (
                SELECT SUM(points) as total_points
                FROM scores 
                WHERE challenge_id = ?
                GROUP BY user_id
                HAVING total_points > 0
            )
        ''', (challenge_id,))
        avg_result = cursor.fetchone()
        if avg_result and avg_result[0]:
            stats['avg_points_per_player'] = round(avg_result[0])
        
        # Highest single day score
        cursor.execute('''
            SELECT u.registered_username, s.date, SUM(s.points) as daily_points
            FROM scores s
            JOIN users u ON s.user_id = u.telegram_id
            WHERE s.challenge_id = ?
            GROUP BY s.user_id, s.date, u.registered_username
            ORDER BY daily_points DESC
            LIMIT 1
        ''', (challenge_id,))
        daily_result = cursor.fetchone()
        if daily_result:
            stats['highest_daily'] = {
                'username': daily_result[0],
                'date': daily_result[1],
                'points': daily_result[2]
            }
        
        # Highest weekly score (Monday-Sunday periods)
        cursor.execute('''
            SELECT 
                u.registered_username,
                strftime('%Y-%W', s.date) as week,
                SUM(s.points) as weekly_points
            FROM scores s
            JOIN users u ON s.user_id = u.telegram_id
            WHERE s.challenge_id = ?
            GROUP BY s.user_id, u.registered_username, strftime('%Y-%W', s.date)
            ORDER BY weekly_points DESC
            LIMIT 1
        ''', (challenge_id,))
        weekly_result = cursor.fetchone()
        if weekly_result:
            stats['highest_weekly'] = {
                'username': weekly_result[0],
                'week': weekly_result[1],
                'points': weekly_result[2]
            }
        
        # Most active day (day with most total points submitted by all users)
        cursor.execute('''
            SELECT date, SUM(points) as day_total
            FROM scores
            WHERE challenge_id = ?
            GROUP BY date
            ORDER BY day_total DESC
            LIMIT 1
        ''', (challenge_id,))
        active_day_result = cursor.fetchone()
        if active_day_result:
            stats['most_active_day'] = {
                'date': active_day_result[0],
                'total_points': active_day_result[1]
            }
        
        # Total challenge points (for points challenges)
        cursor.execute('''
            SELECT SUM(points) FROM scores WHERE challenge_id = ?
        ''', (challenge_id,))
        total_result = cursor.fetchone()
        if total_result and total_result[0]:
            stats['total_points'] = total_result[0]
        
        # Check if this is a change challenge and get change-specific stats
        cursor.execute('SELECT challenge_type FROM challenges WHERE id = ?', (challenge_id,))
        challenge_type = cursor.fetchone()
        
        if challenge_type and challenge_type[0] == 'change':
            # Get gain statistics
            cursor.execute('''
                SELECT 
                    u.registered_username,
                    ((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100 as percent_change
                FROM baseline_values b
                JOIN users u ON b.user_id = u.telegram_id
                WHERE b.challenge_id = ? AND b.baseline_value != 0 AND b.current_value > b.baseline_value
                ORDER BY percent_change DESC
                LIMIT 3
            ''', (challenge_id,))
            gain_results = cursor.fetchall()
            if gain_results:
                stats['top_gains'] = gain_results
            
            # Get loss statistics
            cursor.execute('''
                SELECT 
                    u.registered_username,
                    ((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100 as percent_change
                FROM baseline_values b
                JOIN users u ON b.user_id = u.telegram_id
                WHERE b.challenge_id = ? AND b.baseline_value != 0 AND b.current_value < b.baseline_value
                ORDER BY percent_change ASC
                LIMIT 3
            ''', (challenge_id,))
            loss_results = cursor.fetchall()
            if loss_results:
                stats['top_losses'] = loss_results
            
            # Average change
            cursor.execute('''
                SELECT 
                    AVG(((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100) as avg_change
                FROM baseline_values b
                WHERE b.challenge_id = ? AND b.baseline_value != 0
            ''', (challenge_id,))
            avg_change = cursor.fetchone()
            if avg_change and avg_change[0] is not None:
                stats['avg_change'] = avg_change[0]
            
            # Biggest absolute change
            cursor.execute('''
                SELECT 
                    u.registered_username,
                    b.baseline_value,
                    b.current_value,
                    ABS(((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100) as abs_change
                FROM baseline_values b
                JOIN users u ON b.user_id = u.telegram_id
                WHERE b.challenge_id = ? AND b.baseline_value != 0
                ORDER BY abs_change DESC
                LIMIT 1
            ''', (challenge_id,))
            biggest_change = cursor.fetchone()
            if biggest_change:
                stats['biggest_change'] = {
                    'username': biggest_change[0],
                    'baseline': biggest_change[1],
                    'current': biggest_change[2],
                    'change': biggest_change[3]
                }
        
        conn.close()
        return stats
    
    async def send_challenge_notification(self, application, message_text):
        """Send notification to all groups where the bot is active"""
        # Note: This is a simplified version. In production, you'd want to store group IDs
        # For now, we'll just log the notification
        logger.info(f"Challenge notification: {message_text}")
        # You could implement group ID storage and iterate through them here
        # Example implementation:
        # for group_id in stored_group_ids:
        #     await application.bot.send_message(chat_id=group_id, text=message_text, parse_mode='MarkdownV2')
    
    async def check_and_send_notifications(self, application):
        """Check for pending notifications and send them"""
        challenge = self.get_current_challenge()
        if not challenge:
            return
        
        challenge_id = challenge[0]
        actual_status, status_message = self.get_challenge_status(challenge)
        
        # Update database status if it's different
        if challenge[5] != actual_status: # Note: challenge[5] is the status field
            self.update_challenge_status(challenge_id, actual_status)
        
        # Check for notifications to send
        if actual_status == "active" and not self.has_notification_been_sent(challenge_id, "start"):
            start_date = datetime.strptime(str(challenge[5]), '%Y-%m-%d').strftime('%d/%m/%Y') # challenge[5] is start_date
            end_date = datetime.strptime(str(challenge[6]), '%Y-%m-%d').strftime('%d/%m/%Y') # challenge[6] is end_date
            message = (
                f"🎯 *Challenge Started\\!* 🎯\n\n"
                f"*{escape_markdown_v2(challenge[1])}*\n\n" # challenge[1] is description
                f"*Scoring:* {escape_markdown_v2(challenge[2])}\n" # challenge[2] is scoring_system
                f"*Period:* {escape_markdown_v2(start_date)} to {escape_markdown_v2(end_date)}\n\n"
                f"Good luck to all participants\\! 🍀"
            )
            await self.send_challenge_notification(application, message)
            self.mark_notification_sent(challenge_id, "start")
        
        elif actual_status == "grace_period" and not self.has_notification_been_sent(challenge_id, "ending"):
            message = (
                f"⏰ *Challenge Ending Soon\\!* ⏰\n\n"
                f"*{escape_markdown_v2(challenge[1])}*\n\n"
                f"Challenge has ended\\! Please submit your final scores before midnight to get them included\\. ⏰"
            )
            await self.send_challenge_notification(application, message)
            self.mark_notification_sent(challenge_id, "ending")
        
        elif actual_status == "ended" and not self.has_notification_been_sent(challenge_id, "final_results"):
            # Get final results and announce winners
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Check challenge type
            cursor.execute('SELECT challenge_type FROM challenges WHERE id = ?', (challenge_id,))
            challenge_type_result = cursor.fetchone()
            challenge_type = challenge_type_result[0] if challenge_type_result else 'points'
            
            if challenge_type == 'change':
                # For change challenges, get top performers by absolute change
                cursor.execute('''
                    SELECT 
                        u.registered_username, 
                        ((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100 as percent_change
                    FROM baseline_values b
                    JOIN users u ON b.user_id = u.telegram_id
                    WHERE b.challenge_id = ? AND b.baseline_value != 0
                    ORDER BY ABS(((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100) DESC
                    LIMIT 3
                ''', (challenge_id,))
                
                top_3 = cursor.fetchall()
                
                # Count total participants for change challenges
                cursor.execute('''
                    SELECT COUNT(*) FROM baseline_values WHERE challenge_id = ?
                ''', (challenge_id,))
                total_participants = cursor.fetchone()[0]
            else:
                # For points challenges, get top scorers
                cursor.execute('''
                    SELECT u.registered_username, SUM(s.points) as total_points
                    FROM scores s
                    JOIN users u ON s.user_id = u.telegram_id
                    WHERE s.challenge_id = ?
                    GROUP BY s.user_id, u.registered_username
                    ORDER BY total_points DESC
                    LIMIT 3
                ''', (challenge_id,))
                
                top_3 = cursor.fetchall()
                
                # Count total participants for points challenges
                cursor.execute('''
                    SELECT COUNT(DISTINCT user_id) FROM scores WHERE challenge_id = ?
                ''', (challenge_id,))
                total_participants = cursor.fetchone()[0]
            
            conn.close()
            
            if top_3:
                # Get challenge statistics
                stats = self.get_challenge_stats(challenge_id)
                
                message = f"🏁 *Final Results Are In\\!* 🏁\n\n*{escape_markdown_v2(challenge[1])}*\n\n"
                message += "🏆 *Winners* 🏆\n"
                
                medals = ["🥇", "🥈", "🥉"]
                if challenge_type == 'change':
                    # Display change challenge winners with percentages
                    for i, (username, change) in enumerate(top_3):
                        change_sign = "\+" if change >= 0 else ""
                        message += f"{medals[i]} {escape_markdown_v2(username)}: {change_sign}{change:.2f}%\n"
                else:
                    # Display points challenge winners with points
                    for i, (username, points) in enumerate(top_3):
                        message += f"{medals[i]} {escape_markdown_v2(username)}: {points:,} points\n"
                
                # Add interesting stats
                if stats:
                    message += f"\n📊 *Challenge Stats* 📊\n"
                    
                    # Check if this is a change challenge
                    if 'top_gains' in stats or 'top_losses' in stats:
                        # Change challenge stats
                        if 'avg_change' in stats:
                            avg_sign = "\+" if stats['avg_change'] >= 0 else ""
                            message += f"Average Change: {avg_sign}{stats['avg_change']:.2f}%\n"
                        
                        if 'biggest_change' in stats:
                            biggest = stats['biggest_change']
                            message += f"Biggest Change: {escape_markdown_v2(biggest['username'])} \\- {biggest['change']:.2f}%\n"
                        
                        if 'top_gains' in stats and stats['top_gains']:
                            message += f"\n📈 *Top Gains:*\n"
                            for username, change in stats['top_gains']:
                                message += f"• {escape_markdown_v2(username)}: \+{change:.2f}%\n"
                        
                        if 'top_losses' in stats and stats['top_losses']:
                            message += f"\n📉 *Top Losses:*\n"  
                            for username, change in stats['top_losses']:
                                message += f"• {escape_markdown_v2(username)}: {change:.2f}%\n"
                    else:
                        # Points challenge stats
                        if 'total_points' in stats:
                            message += f"Total Points Earned: {stats['total_points']:,}\n"
                        
                        if 'avg_points_per_player' in stats:
                            message += f"Average per Player: {stats['avg_points_per_player']:,} points\n"
                        
                        if 'highest_daily' in stats:
                            daily = stats['highest_daily']
                            # Convert date to dd,mm,yyyy format
                            try:
                                date_obj = datetime.strptime(daily['date'], '%Y-%m-%d')
                                formatted_date = date_obj.strftime('%d/%m/%Y')
                            except:
                                formatted_date = daily['date']
                            message += f"Best Single Day: {escape_markdown_v2(daily['username'])} \\- {daily['points']:,} pts \({escape_markdown_v2(formatted_date)}\)\n"
                        
                        if 'highest_weekly' in stats:
                            weekly = stats['highest_weekly']
                            message += f"Best Weekly Total: {escape_markdown_v2(weekly['username'])} \\- {weekly['points']:,} pts\n"
                        
                        if 'most_active_day' in stats:
                            active = stats['most_active_day']
                            try:
                                date_obj = datetime.strptime(active['date'], '%Y-%m-%d')
                                formatted_date = date_obj.strftime('%d/%m/%Y')
                            except:
                                formatted_date = active['date']
                            message += f"Most Active Day: {escape_markdown_v2(formatted_date)} \({active['total_points']:,} total pts\)\n"
                
                message += f"\n🎉 Congratulations to all {total_participants} participants who competed\\! 🎉\n"
                message += "Thank you for making this challenge amazing\\! 🙌"
            else:
                message = f"🏁 *Challenge Complete\\!* 🏁\n\n*{escape_markdown_v2(challenge[1])}*\n\nNo scores were submitted for this challenge\\."
            
            await self.send_challenge_notification(application, message)
            self.mark_notification_sent(challenge_id, "final_results")
            # Mark challenge as completed
            self.update_challenge_status(challenge_id, "completed")

    def get_week_dates(self, offset=0):
        """Get start and end dates for current or previous week"""
        today = datetime.now().date()
        days_since_monday = today.weekday()
        monday = today - timedelta(days=days_since_monday + (7 * offset))
        sunday = monday + timedelta(days=6)
        return monday, sunday

    def parse_date_input(self, date_str):
        """Parse date input (single day or range)"""
        try:
            if '-' in date_str:
                start, end = map(int, date_str.split('-'))
                if start < 1 or end > 31 or start > end:
                    return None
                return list(range(start, end + 1))
            else:
                day = int(date_str)
                if day < 1 or day > 31:
                    return None
                return [day]
        except ValueError:
            return None

    def ensure_fixed_admin(self, user_id, username):
        """Ensure lucaspuu is always an admin"""
        if username == 'lucaspuu':
            conn = self.get_db_connection()
            cursor = conn.cursor()
            try:
                # Add user to users table if not exists
                cursor.execute('''
                    INSERT OR IGNORE INTO users (telegram_id, username) 
                    VALUES (?, ?)
                ''', (user_id, username))
                
                # Make them admin
                cursor.execute('''
                    INSERT OR IGNORE INTO admins (user_id, added_by) 
                    VALUES (?, ?)
                ''', (user_id, user_id))
                
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Error ensuring fixed admin: {e}")
            finally:
                conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    # Ensure lucaspuu is always an admin
    bot_instance = context.bot_data.get('bot_instance')
    if bot_instance and update.effective_user.username:
        bot_instance.ensure_fixed_admin(update.effective_user.id, update.effective_user.username)
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "Welcome to the Monthly Competition Bot\\!\n\n"
            "Use /register to register your username for competitions\\.\n"
            "Use /help to see all available commands\\.", parse_mode='MarkdownV2'
        )
    else:
        await update.message.reply_text("Bot is active in this group\\!", parse_mode='MarkdownV2')

async def new_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot being added to group"""
    bot_instance = context.bot_data.get('bot_instance')
    
    # Ensure lucaspuu is always an admin
    if bot_instance and update.effective_user.username:
        bot_instance.ensure_fixed_admin(update.effective_user.id, update.effective_user.username)
    
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:  # Bot was added to group
            # Make the user who added the bot an admin
            user_id = update.effective_user.id
            
            conn = bot_instance.get_db_connection()
            cursor = conn.cursor()
            
            try:
                # Add user to users table if not exists
                cursor.execute('''
                    INSERT OR IGNORE INTO users (telegram_id, username) 
                    VALUES (?, ?)
                ''', (user_id, update.effective_user.username))
                
                # Make them admin
                cursor.execute('''
                    INSERT OR IGNORE INTO admins (user_id, added_by) 
                    VALUES (?, ?)
                ''', (user_id, user_id))
                
                conn.commit()
                
                await update.message.reply_text(
                    f"Hello\\! I'm the Monthly Competition Bot\\.\n\n"
                    f"{escape_markdown_v2(update.effective_user.first_name)}, you have been made an admin\\.\n"
                    f"Use /startchallenge in a private message to create the first challenge\\!", parse_mode='MarkdownV2'
                )
                
            except sqlite3.Error as e:
                logger.error(f"Error setting up admin: {e}")
            finally:
                conn.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    bot = context.bot_data.get('bot_instance')
    is_admin = bot.is_admin(update.effective_user.id) if bot else False
    
    # Check if current challenge is a change challenge
    current_challenge = bot.get_current_challenge() if bot else None
    is_change_challenge = (current_challenge and len(current_challenge) > 3 and 
                          current_challenge[3] == 'change') # challenge[3] is challenge_type
    
    if update.effective_chat.type == 'private':
        # Private message - show all relevant commands
        help_text = """🎯 *Competition Bot Help* 🎯

📊 *Leaderboards & Stats:*
/stats \\- Monthly leaderboard
/statsweek \\- Current week points
/statslastweek \\- Previous week points"""
        
        # Add change challenge stats only if current challenge is a change type
        if is_change_challenge:
            help_text += """
/statsgain \\- Top gainers \(change challenges\)
/statsloss \\- Top losers \(change challenges\) 
/statschange \\- Overall change leaderboard"""
        
        help_text += """

🎮 *Challenge Information:*
/challenge \\- Current challenge details
/pastchallenges \\- View past challenge results

💡 *Challenge Suggestions:*
/nextchallenge \\- Vote on upcoming challenges
/newsuggest \\- Suggest a new challenge idea

👤 *Personal Management \(DM only\):*
/register \\- Register your username
/addscore \\- Add points for specific dates
/removescore \\- Remove points from dates
/editscore \\- Edit existing points"""
        
        # Add change challenge management commands only if current challenge is a change type
        if is_change_challenge:
            help_text += """
/setbaseline \\- Set baseline value \(change challenges\)
/updatevalue \\- Update current value \(change challenges\)"""

        
        # Add admin commands only for admins
        if is_admin:
            help_text += """

👑 *Admin Commands \(DM only\):*
/admins \\- List current admins
/addadmin \\- Add new admin
/removeadmin \\- Remove admin privileges
/startchallenge \\- Create and start new challenge
/editchallenge \\- Edit existing challenge details
/removechallenge \\- Remove challenge permanently
/removeentry \\- Remove user from competition
/showfeedback \\- View submitted feedback"""
        
        help_text += """
🛠️ *General Commands:*
/cancel \\- Cancels the current operation\\. Can be useful if something seems to be stuck
/feedback <feedback> \\- Sends anonymous feedback to my developer"""
        
        
    else:
        # Group message - show group-relevant commands only
        help_text = """🎯 *Competition Bot \\- Group Commands* 🎯

📊 *Leaderboards:*
/stats \\- Monthly leaderboard
/statsweek \\- Current week points
/statslastweek \\- Previous week points"""
        
        # Add change challenge stats only if current challenge is a change type
        if is_change_challenge:
            help_text += """
/statsgain \\- Top gainers \(change challenges\)
/statsloss \\- Top losers \(change challenges\)
/statschange \\- Overall change leaderboard"""
        
        help_text += """

🎮 *Challenges:*
/challenge \\- Current challenge details
/nextchallenge \\- Vote on upcoming challenges
/pastchallenges \\- View past challenge results

🗳️ *Voting Instructions:*
\\- After /nextchallenge: Reply with number to vote
\\- Reply 'new' for challenge suggestion help
\\- After /pastchallenges: Reply with number for details

🛠️ *General Commands:*
/cancel \\- Cancels the current operation
/feedback <feedback> \\- Send anonymous feedback

💬 *Need More Help?*
Send me a private message for full command list\\!"""
    
    await update.message.reply_text(help_text, parse_mode='MarkdownV2')

# Registration conversation
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start registration process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    await update.message.reply_text("Please enter the username you'd like to register for competitions:", parse_mode='MarkdownV2')
    return REGISTER_USERNAME

async def register_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle username registration"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with your username:", parse_mode='MarkdownV2')
        return REGISTER_USERNAME
    
    username = update.message.text.strip()
    user_id = update.effective_user.id
    tg_username = update.effective_user.username
    
    # Validate username length
    if len(username) < 3 or len(username) > 20:
        await update.message.reply_text("Username must be between 3\\-20 characters\\. Try again:", parse_mode='MarkdownV2')
        return REGISTER_USERNAME
    
    # Validate username contains only allowed characters
    if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
        await update.message.reply_text("Username can only contain letters, numbers, dots, dashes, and underscores\\. Try again:", parse_mode='MarkdownV2')
        return REGISTER_USERNAME
    
    bot = context.bot_data.get('bot_instance')
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if username already exists
        cursor.execute('SELECT 1 FROM users WHERE registered_username = ?', (username,))
        if cursor.fetchone():
            await update.message.reply_text(f"Username '{escape_markdown_v2(username)}' is already taken\\. Please choose another:", parse_mode='MarkdownV2')
            return REGISTER_USERNAME
        
        # Register user
        cursor.execute('''
            INSERT OR REPLACE INTO users (telegram_id, username, registered_username) 
            VALUES (?, ?, ?)
        ''', (user_id, tg_username, username))
        
        conn.commit()
        await update.message.reply_text(f"Successfully registered with username: {escape_markdown_v2(username)}", parse_mode='MarkdownV2')
        
    except sqlite3.Error as e:
        await update.message.reply_text("Registration failed\\. Please try again\\.", parse_mode='MarkdownV2')
        logger.error(f"Registration error: {e}")
    finally:
        conn.close()
    
    return ConversationHandler.END

async def register_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel registration"""
    await update.message.reply_text("Registration cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Add score conversation
async def add_score_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start add score process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Enter the date\\(s\\) for scoring:\n"
        "\\- Single day: 15\n" 
        "\\- Date range: 6\\-10\n"
        "\\- Cancel with /cancel", parse_mode='MarkdownV2'
    )
    return ADD_SCORE_DATE

async def add_score_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle date input for add score"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the date\\(s\\):", parse_mode='MarkdownV2')
        return ADD_SCORE_DATE
    
    date_str = update.message.text.strip()
    
    if not date_str:
        await update.message.reply_text("Date cannot be empty\\. Please enter a date:", parse_mode='MarkdownV2')
        return ADD_SCORE_DATE
    
    bot = context.bot_data.get('bot_instance')
    
    dates = bot.parse_date_input(date_str)
    if not dates:
        await update.message.reply_text("Invalid date format\\. Please enter a day \(1\\-31\) or range \(6\\-10\):", parse_mode='MarkdownV2')
        return ADD_SCORE_DATE
    
    context.user_data['score_dates'] = dates
    await update.message.reply_text(f"Enter points to add \(will be distributed across {len(dates)} day\\(s\)\):", parse_mode='MarkdownV2')
    return ADD_SCORE_POINTS

async def add_score_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle points input for add score"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with your points:", parse_mode='MarkdownV2')
        return ADD_SCORE_POINTS
    
    try:
        points_str = update.message.text.strip()
        
        # Check for empty input
        if not points_str:
            await update.message.reply_text("Please enter a number for points:", parse_mode='MarkdownV2')
            return ADD_SCORE_POINTS
        
        points = int(points_str)
        
        if points <= 0:
            await update.message.reply_text("Points must be positive\\. Please enter a valid number:", parse_mode='MarkdownV2')
            return ADD_SCORE_POINTS
        
        if points > 1000000:
            await update.message.reply_text("Maximum 1,000,000 total points allowed\\. Please enter a lower amount:", parse_mode='MarkdownV2')
            return ADD_SCORE_POINTS
        
        dates = context.user_data.get('score_dates', [])
        if not dates:
            await update.message.reply_text("Session expired\\. Please start over with /addscore", parse_mode='MarkdownV2')
            return ConversationHandler.END
        
        points_per_day = points // len(dates)
        
        # Check daily limit
        if points_per_day > 100000:
            await update.message.reply_text("Maximum 100,000 points per day\\. Please enter a lower amount:", parse_mode='MarkdownV2')
            return ADD_SCORE_POINTS
        
        context.user_data['score_points'] = points
        context.user_data['points_per_day'] = points_per_day
        
        date_str = ', '.join(map(str, dates))
        await update.message.reply_text(
            f"Add {points} points distributed across days {date_str} "
            f"\({points_per_day} points per day\)?\n"
            f"Reply 'y' to confirm or 'n' to cancel\\.", parse_mode='MarkdownV2'
        )
        return ADD_SCORE_CONFIRM
        
    except ValueError:
        await update.message.reply_text("Please enter a valid number \(integers only\):", parse_mode='MarkdownV2')
        return ADD_SCORE_POINTS
    except Exception as e:
        logger.error(f"Error in add_score_points: {e}")
        await update.message.reply_text("An error occurred\\. Please try again or contact an admin\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END

async def add_score_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm add score operation"""
    response = update.message.text.strip().lower()
    
    if response == 'y':
        bot = context.bot_data.get('bot_instance')
        user_id = update.effective_user.id
        dates = context.user_data['score_dates']
        points_per_day = context.user_data['points_per_day']
        
        current_challenge = bot.get_current_challenge()
        if not current_challenge:
            await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
            return ConversationHandler.END
        
        # Check if we're in a valid period for score entry
        actual_status, status_message = bot.get_challenge_status(current_challenge)
        if actual_status not in ["active", "grace_period"]:
            await update.message.reply_text(
                f"Cannot add scores right now\\. Challenge status: {status_message}", parse_mode='MarkdownV2'
            )
            return ConversationHandler.END
        
        challenge_id = current_challenge[0]
        
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Add scores for each date
            current_month = datetime.now().month
            current_year = datetime.now().year
            
            for day in dates:
                date_obj = datetime(current_year, current_month, day).date()
                cursor.execute('''
                    INSERT INTO scores (user_id, date, points, challenge_id) 
                    VALUES (?, ?, ?, ?)
                ''', (user_id, date_obj, points_per_day, challenge_id))
            
            conn.commit()
            await update.message.reply_text("Points added successfully\\!", parse_mode='MarkdownV2')
            
        except sqlite3.Error as e:
            await update.message.reply_text("Error adding points\\. Please try again\\.", parse_mode='MarkdownV2')
            logger.error(f"Add score error: {e}")
        finally:
            conn.close()
    
    elif response == 'n':
        await update.message.reply_text("Points addition cancelled\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return ADD_SCORE_CONFIRM
    
    return ConversationHandler.END

async def add_score_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel add score"""
    await update.message.reply_text("Add score cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Stats commands
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show monthly leaderboard"""
    bot = context.bot_data.get('bot_instance')
    current_challenge = bot.get_current_challenge()
    
    if not current_challenge:
        await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
        return
    
    challenge_id = current_challenge[0]
    
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    # Get monthly totals
    cursor.execute('''
        SELECT u.registered_username, SUM(s.points) as total_points
        FROM scores s
        JOIN users u ON s.user_id = u.telegram_id
        WHERE s.challenge_id = ?
        GROUP BY s.user_id, u.registered_username
        ORDER BY total_points DESC
        LIMIT 20
    ''', (challenge_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        await update.message.reply_text("No scores recorded yet\\.", parse_mode='MarkdownV2')
        return
    
    leaderboard = "*🏆 Monthly Leaderboard 🏆*\n\n"
    for i, (username, points) in enumerate(results, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}\\."
        leaderboard += f"{medal} {escape_markdown_v2(username)}: {points:,} points\n"
    
    await update.message.reply_text(leaderboard, parse_mode='MarkdownV2')

async def stats_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current week leaderboard"""
    bot = context.bot_data.get('bot_instance')
    current_challenge = bot.get_current_challenge()
    
    if not current_challenge:
        await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
        return
    
    challenge_id = current_challenge[0]
    monday, sunday = bot.get_week_dates(0)
    
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.registered_username, SUM(s.points) as total_points
        FROM scores s
        JOIN users u ON s.user_id = u.telegram_id
        WHERE s.challenge_id = ? AND s.date BETWEEN ? AND ?
        GROUP BY s.user_id, u.registered_username
        ORDER BY total_points DESC
        LIMIT 20
    ''', (challenge_id, monday, sunday))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        await update.message.reply_text("No scores for this week yet\\.", parse_mode='MarkdownV2')
        return
    
    leaderboard = f"📅 *This Week* \({escape_markdown_v2(monday.strftime('%d/%m/%Y'))} \\- {escape_markdown_v2(sunday.strftime('%d/%m/%Y'))}\) 📅\n\n"
    for i, (username, points) in enumerate(results, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}\\."
        leaderboard += f"{medal} {escape_markdown_v2(username)}: {points:,} points\n"
    
    await update.message.reply_text(leaderboard, parse_mode='MarkdownV2')

async def stats_last_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show previous week leaderboard"""
    bot = context.bot_data.get('bot_instance')
    current_challenge = bot.get_current_challenge()
    
    if not current_challenge:
        await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
        return
    
    challenge_id = current_challenge[0]
    monday, sunday = bot.get_week_dates(1)  # Previous week
    
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.registered_username, SUM(s.points) as total_points
        FROM scores s
        JOIN users u ON s.user_id = u.telegram_id
        WHERE s.challenge_id = ? AND s.date BETWEEN ? AND ?
        GROUP BY s.user_id, u.registered_username
        ORDER BY total_points DESC
        LIMIT 20
    ''', (challenge_id, monday, sunday))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        await update.message.reply_text("No scores for last week\\.", parse_mode='MarkdownV2')
        return
    
    leaderboard = f"📅 *Last Week* \({escape_markdown_v2(monday.strftime('%d/%m/%Y'))} \\- {escape_markdown_v2(sunday.strftime('%d/%m/%Y'))}\) 📅\n\n"
    for i, (username, points) in enumerate(results, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}\\."
        leaderboard += f"{medal} {escape_markdown_v2(username)}: {points:,} points\n"
    
    await update.message.reply_text(leaderboard, parse_mode='MarkdownV2')

# Change challenge leaderboards (gain/loss)
async def stats_gain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show gain leaderboard for change challenges"""
    bot = context.bot_data.get('bot_instance')
    current_challenge = bot.get_current_challenge()
    
    if not current_challenge:
        await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
        return
    
    # Check if it's a change challenge
    if len(current_challenge) < 4 or current_challenge[3] != 'change':
        await update.message.reply_text("This command is only for change\\-based challenges\\.", parse_mode='MarkdownV2')
        return
    
    challenge_id = current_challenge[0]
    
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    # Get users with positive percentage changes
    cursor.execute('''
        SELECT 
            u.registered_username, 
            b.baseline_value,
            b.current_value,
            ((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100 as percent_change
        FROM baseline_values b
        JOIN users u ON b.user_id = u.telegram_id
        WHERE b.challenge_id = ? AND b.baseline_value != 0 AND b.current_value > b.baseline_value
        ORDER BY percent_change DESC
        LIMIT 20
    ''', (challenge_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        await update.message.reply_text("No gains recorded yet in this challenge\\.", parse_mode='MarkdownV2')
        return
    
    leaderboard = f"📈 *Gain Leaderboard* 📈\n\n*{escape_markdown_v2(current_challenge[1])}*\n\n"
    for i, (username, baseline, current, change) in enumerate(results, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}\\."
        leaderboard += f"{medal} {escape_markdown_v2(username)}: \\+{change:.2f}%\n"
        leaderboard += f"   {baseline} → {current}\n\n"
    
    await update.message.reply_text(leaderboard, parse_mode='MarkdownV2')

async def stats_loss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show loss leaderboard for change challenges"""
    bot = context.bot_data.get('bot_instance')
    current_challenge = bot.get_current_challenge()
    
    if not current_challenge:
        await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
        return
    
    # Check if it's a change challenge
    if len(current_challenge) < 4 or current_challenge[3] != 'change':
        await update.message.reply_text("This command is only for change\\-based challenges\\.", parse_mode='MarkdownV2')
        return
    
    challenge_id = current_challenge[0]
    
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    # Get users with negative percentage changes (sorted by most loss)
    cursor.execute('''
        SELECT 
            u.registered_username, 
            b.baseline_value,
            b.current_value,
            ((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100 as percent_change
        FROM baseline_values b
        JOIN users u ON b.user_id = u.telegram_id
        WHERE b.challenge_id = ? AND b.baseline_value != 0 AND b.current_value < b.baseline_value
        ORDER BY percent_change ASC
        LIMIT 20
    ''', (challenge_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        await update.message.reply_text("No losses recorded yet in this challenge\\.", parse_mode='MarkdownV2')
        return
    
    leaderboard = f"📉 *Loss Leaderboard* 📉\n\n*{escape_markdown_v2(current_challenge[1])}*\n\n"
    for i, (username, baseline, current, change) in enumerate(results, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}\\."
        leaderboard += f"{medal} {escape_markdown_v2(username)}: {change:.2f}%\n"
        leaderboard += f"   {baseline} → {current}\n\n"
    
    await update.message.reply_text(leaderboard, parse_mode='MarkdownV2')

async def stats_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show combined change leaderboard for change challenges"""
    bot = context.bot_data.get('bot_instance')
    current_challenge = bot.get_current_challenge()
    
    if not current_challenge:
        await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
        return
    
    # Check if it's a change challenge
    if len(current_challenge) < 4 or current_challenge[3] != 'change':
        await update.message.reply_text("This command is only for change\\-based challenges\\.", parse_mode='MarkdownV2')
        return
    
    challenge_id = current_challenge[0]
    
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    # Get all users with their percentage changes
    cursor.execute('''
        SELECT 
            u.registered_username, 
            b.baseline_value,
            b.current_value,
            ((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100 as percent_change
        FROM baseline_values b
        JOIN users u ON b.user_id = u.telegram_id
        WHERE b.challenge_id = ? AND b.baseline_value != 0
        ORDER BY ABS(((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100) DESC
        LIMIT 20
    ''', (challenge_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        await update.message.reply_text("No changes recorded yet in this challenge\\.", parse_mode='MarkdownV2')
        return
    
    leaderboard = f"🔄 *Change Leaderboard* 🔄\n\n*{escape_markdown_v2(current_challenge[1])}*\n\n"
    for i, (username, baseline, current, change) in enumerate(results, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}\\."
        change_sign = "\+" if change >= 0 else ""
        leaderboard += f"{medal} {escape_markdown_v2(username)}: {change_sign}{change:.2f}%\n"
        leaderboard += f"   {baseline} → {current}\n\n"
    
    await update.message.reply_text(leaderboard, parse_mode='MarkdownV2')

# Remove score conversation
async def remove_score_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start remove score process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Enter the date\\(s\\) to remove points from:\n"
        "\\- Single day: 15\n"
        "\\- Date range: 6\\-10\n"
        "\\- Cancel with /cancel", parse_mode='MarkdownV2'
    )
    return REMOVE_SCORE_DATE

async def remove_score_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle date input for remove score"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the date\\(s\\):", parse_mode='MarkdownV2')
        return REMOVE_SCORE_DATE
    
    date_str = update.message.text.strip()
    
    if not date_str:
        await update.message.reply_text("Date cannot be empty\\. Please enter a date:", parse_mode='MarkdownV2')
        return REMOVE_SCORE_DATE
    
    bot = context.bot_data.get('bot_instance')
    
    dates = bot.parse_date_input(date_str)
    if not dates:
        await update.message.reply_text("Invalid date format\\. Please enter a day \(1\\-31\) or range \(6\\-10\):", parse_mode='MarkdownV2')
        return REMOVE_SCORE_DATE
    
    context.user_data['remove_dates'] = dates
    date_str = ', '.join(map(str, dates))
    
    await update.message.reply_text(
        f"Remove all points for days {date_str}?\n"
        f"Reply 'y' to confirm or 'n' to cancel\\.", parse_mode='MarkdownV2'
    )
    return REMOVE_SCORE_CONFIRM

async def remove_score_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm remove score operation"""
    response = update.message.text.strip().lower()
    
    if response == 'y':
        bot = context.bot_data.get('bot_instance')
        user_id = update.effective_user.id
        dates = context.user_data['remove_dates']
        
        current_challenge = bot.get_current_challenge()
        if not current_challenge:
            await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
            return ConversationHandler.END
        
        challenge_id = current_challenge[0]
        
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        try:
            current_month = datetime.now().month
            current_year = datetime.now().year
            removed_count = 0
            
            for day in dates:
                date_obj = datetime(current_year, current_month, day).date()
                cursor.execute('''
                    DELETE FROM scores 
                    WHERE user_id = ? AND date = ? AND challenge_id = ?
                ''', (user_id, date_obj, challenge_id))
                removed_count += cursor.rowcount
            
            conn.commit()
            await update.message.reply_text(f"Removed {removed_count} score entries successfully\\!", parse_mode='MarkdownV2')
            
        except sqlite3.Error as e:
            await update.message.reply_text("Error removing points\\. Please try again\\.", parse_mode='MarkdownV2')
            logger.error(f"Remove score error: {e}")
        finally:
            conn.close()
    
    elif response == 'n':
        await update.message.reply_text("Score removal cancelled\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return REMOVE_SCORE_CONFIRM
    
    return ConversationHandler.END

async def remove_score_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel remove score"""
    await update.message.reply_text("Remove score cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Edit score conversation
async def edit_score_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start edit score process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Enter the date\\(s\\) to edit points for:\n"
        "\\- Single day: 15\n"
        "\\- Date range: 6\\-10\n"
        "\\- Cancel with /cancel", parse_mode='MarkdownV2'
    )
    return EDIT_SCORE_DATE

async def edit_score_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle date input for edit score"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the date\\(s\\):", parse_mode='MarkdownV2')
        return EDIT_SCORE_DATE
    
    date_str = update.message.text.strip()
    
    if not date_str:
        await update.message.reply_text("Date cannot be empty\\. Please enter a date:", parse_mode='MarkdownV2')
        return EDIT_SCORE_DATE
    
    bot = context.bot_data.get('bot_instance')
    user_id = update.effective_user.id
    
    dates = bot.parse_date_input(date_str)
    if not dates:
        await update.message.reply_text("Invalid date format\\. Please enter a day \(1\\-31\) or range \(6\\-10\):", parse_mode='MarkdownV2')
        return EDIT_SCORE_DATE
    
    # Get current points for these dates
    current_challenge = bot.get_current_challenge()
    if not current_challenge:
        await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    challenge_id = current_challenge[0]
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    total_current_points = 0
    
    for day in dates:
        date_obj = datetime(current_year, current_month, day).date()
        cursor.execute('''
            SELECT SUM(points) FROM scores 
            WHERE user_id = ? AND date = ? AND challenge_id = ?
        ''', (user_id, date_obj, challenge_id))
        result = cursor.fetchone()
        if result and result[0]:
            total_current_points += result[0]
    
    conn.close()
    
    context.user_data['edit_dates'] = dates
    date_str = ', '.join(map(str, dates))
    
    await update.message.reply_text(
        f"Current points for days {date_str}: {total_current_points}\n"
        f"Enter new total points for this period:", parse_mode='MarkdownV2'
    )
    return EDIT_SCORE_NEW_POINTS

async def edit_score_new_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new points input for edit score"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the new points:", parse_mode='MarkdownV2')
        return EDIT_SCORE_NEW_POINTS
    
    try:
        points_str = update.message.text.strip()
        
        if not points_str:
            await update.message.reply_text("Please enter a number for points:", parse_mode='MarkdownV2')
            return EDIT_SCORE_NEW_POINTS
        
        new_points = int(points_str)
        
        if new_points < 0:
            await update.message.reply_text("Points cannot be negative\\. Please enter a valid number:", parse_mode='MarkdownV2')
            return EDIT_SCORE_NEW_POINTS
        
        if new_points > 1000000:
            await update.message.reply_text("Maximum 1,000,000 total points allowed\\. Please enter a lower amount:", parse_mode='MarkdownV2')
            return EDIT_SCORE_NEW_POINTS
        
        dates = context.user_data.get('edit_dates', [])
        if not dates:
            await update.message.reply_text("Session expired\\. Please start over with /editscore", parse_mode='MarkdownV2')
            return ConversationHandler.END
        
        points_per_day = new_points // len(dates)
        
        if points_per_day > 100000:
            await update.message.reply_text("Maximum 100,000 points per day\\. Please enter a lower amount:", parse_mode='MarkdownV2')
            return EDIT_SCORE_NEW_POINTS
        
        context.user_data['edit_new_points'] = new_points
        context.user_data['edit_points_per_day'] = points_per_day
        
        date_str = ', '.join(map(str, dates))
        await update.message.reply_text(
            f"Update points for days {date_str} to {new_points} total "
            f"\({points_per_day} points per day\)?\n"
            f"Reply 'y' to confirm or 'n' to cancel\\.", parse_mode='MarkdownV2'
        )
        return EDIT_SCORE_CONFIRM
        
    except ValueError:
        await update.message.reply_text("Please enter a valid number \(integers only\):", parse_mode='MarkdownV2')
        return EDIT_SCORE_NEW_POINTS
    except Exception as e:
        logger.error(f"Error in edit_score_new_points: {e}")
        await update.message.reply_text("An error occurred\\. Please try again or contact an admin\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END

async def edit_score_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm edit score operation"""
    response = update.message.text.strip().lower()
    
    if response == 'y':
        bot = context.bot_data.get('bot_instance')
        user_id = update.effective_user.id
        dates = context.user_data['edit_dates']
        points_per_day = context.user_data['edit_points_per_day']
        
        current_challenge = bot.get_current_challenge()
        if not current_challenge:
            await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
            return ConversationHandler.END
        
        challenge_id = current_challenge[0]
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        try:
            current_month = datetime.now().month
            current_year = datetime.now().year
            
            # Remove existing scores for these dates
            for day in dates:
                date_obj = datetime(current_year, current_month, day).date()
                cursor.execute('''
                    DELETE FROM scores 
                    WHERE user_id = ? AND date = ? AND challenge_id = ?
                ''', (user_id, date_obj, challenge_id))
            
            # Add new scores
            if points_per_day > 0:  # Only add if points > 0
                for day in dates:
                    date_obj = datetime(current_year, current_month, day).date()
                    cursor.execute('''
                        INSERT INTO scores (user_id, date, points, challenge_id) 
                        VALUES (?, ?, ?, ?)
                    ''', (user_id, date_obj, points_per_day, challenge_id))
            
            conn.commit()
            await update.message.reply_text("Points updated successfully\\!", parse_mode='MarkdownV2')
            
        except sqlite3.Error as e:
            await update.message.reply_text("Error updating points\\. Please try again\\.", parse_mode='MarkdownV2')
            logger.error(f"Edit score error: {e}")
        finally:
            conn.close()
    
    elif response == 'n':
        await update.message.reply_text("Points edit cancelled\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return EDIT_SCORE_CONFIRM
    
    return ConversationHandler.END

async def edit_score_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel edit score"""
    await update.message.reply_text("Edit score cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Start challenge conversation
async def start_challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start challenge creation process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    bot = context.bot_data.get('bot_instance')
    if not bot.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is for admins only.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    await update.message.reply_text("Enter the challenge description:", parse_mode='MarkdownV2')
    return START_CHALLENGE_DESC

async def start_challenge_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle challenge description input"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the challenge description:", parse_mode='MarkdownV2')
        return START_CHALLENGE_DESC
    
    description = update.message.text.strip()
    
    if not description:
        await update.message.reply_text("Description cannot be empty\\. Please try again:", parse_mode='MarkdownV2')
        return START_CHALLENGE_DESC
    
    if len(description) < 10:
        await update.message.reply_text("Description should be at least 10 characters\\. Please try again:", parse_mode='MarkdownV2')
        return START_CHALLENGE_DESC
    
    if len(description) > 500:
        await update.message.reply_text("Description should be 500 characters or less\\. Please try again:", parse_mode='MarkdownV2')
        return START_CHALLENGE_DESC
    
    context.user_data['challenge_desc'] = description
    
    # Ask for challenge type
    await update.message.reply_text(
        "Choose the challenge type:\n\n"
        "**1\\. Points Challenge**\n"
        "Users earn points for activities \(e\\.g\\., 100 points per workout, 50 points per healthy meal\)\n\n"
        "**2\\. Change Challenge**\n"
        "Users track changes in a measurable value \(e\\.g\\., weight loss/gain, steps improvement\)\n\n"
        "Reply with '1' for Points or '2' for Change:", parse_mode='MarkdownV2'
    )
    return START_CHALLENGE_TYPE

async def start_challenge_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle challenge type selection"""
    choice = update.message.text.strip()
    
    if choice == '1':
        context.user_data['challenge_type'] = 'points'
        context.user_data['type_description'] = 'Points-based challenge where users earn points for activities'
        await update.message.reply_text("Enter the scoring system \(e\\.g\\., '100 points per workout, 50 points per healthy meal'\):", parse_mode='MarkdownV2')
    elif choice == '2':
        context.user_data['challenge_type'] = 'change'
        context.user_data['type_description'] = 'Change-based challenge tracking percentage improvements'
        await update.message.reply_text("Enter what will be measured \(e\\.g\\., 'Weight in kg', 'Daily steps', 'Body fat %'\):", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply with '1' for Points or '2' for Change:", parse_mode='MarkdownV2')
        return START_CHALLENGE_TYPE
    
    return START_CHALLENGE_SCORING

async def start_challenge_scoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle scoring system input"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the scoring system:", parse_mode='MarkdownV2')
        return START_CHALLENGE_SCORING
    
    scoring = update.message.text.strip()
    
    if not scoring:
        await update.message.reply_text("Scoring system cannot be empty\\. Please try again:", parse_mode='MarkdownV2')
        return START_CHALLENGE_SCORING
    
    if len(scoring) < 5:
        await update.message.reply_text("Scoring system should be at least 5 characters\\. Please try again:", parse_mode='MarkdownV2')
        return START_CHALLENGE_SCORING
    
    if len(scoring) > 200:
        await update.message.reply_text("Scoring system should be 200 characters or less\\. Please try again:", parse_mode='MarkdownV2')
        return START_CHALLENGE_SCORING
    
    context.user_data['challenge_scoring'] = scoring
    await update.message.reply_text("Enter the time period \(e\\.g\\., '01/01/2025 to 31/01/2025'\):", parse_mode='MarkdownV2')
    return START_CHALLENGE_PERIOD

async def start_challenge_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle time period input"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the time period:", parse_mode='MarkdownV2')
        return START_CHALLENGE_PERIOD
    
    period = update.message.text.strip()
    
    if not period:
        await update.message.reply_text("Period cannot be empty\\. Please enter a time period:", parse_mode='MarkdownV2')
        return START_CHALLENGE_PERIOD
    
    context.user_data['challenge_period'] = period
    
    # Parse dates (simple validation)
    try:
        if ' to ' in period:
            start_str, end_str = period.split(' to ')
            start_date = datetime.strptime(start_str.strip(), '%d/%m/%Y').date()
            end_date = datetime.strptime(end_str.strip(), '%d/%m/%Y').date()
            if start_date >= end_date:
                raise ValueError("Start date must be before end date")
            # Check if dates are not too far in the future
            today = datetime.now().date()
            if start_date > today + timedelta(days=365):
                raise ValueError("Start date cannot be more than a year in the future")
            context.user_data['start_date'] = start_date
            context.user_data['end_date'] = end_date
        else:
            raise ValueError("Invalid format")
    except ValueError as e:
        if "Start date must be before end date" in str(e):
            await update.message.reply_text("Start date must be before end date\\. Please try again:", parse_mode='MarkdownV2')
        elif "Start date cannot be more than a year" in str(e):
            await update.message.reply_text("Start date cannot be more than a year in the future\\. Please try again:", parse_mode='MarkdownV2')
        else:
            await update.message.reply_text("Invalid date format\\. Use 'dd,mm,yyyy to dd,mm,yyyy':", parse_mode='MarkdownV2')
        return START_CHALLENGE_PERIOD
    
    # Show confirmation
    desc = context.user_data['challenge_desc']
    scoring = context.user_data['challenge_scoring']
    
    await update.message.reply_text(
        f"Create new challenge?\n\n"
        f"**Description:** {escape_markdown_v2(desc)}\n"
        f"**Scoring:** {escape_markdown_v2(scoring)}\n"
        f"**Period:** {escape_markdown_v2(period)}\n\n"
        f"Reply 'y' to confirm or 'n' to cancel\\.", parse_mode='MarkdownV2'
    )
    return START_CHALLENGE_CONFIRM

async def start_challenge_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm challenge creation"""
    response = update.message.text.strip().lower()
    
    if response == 'y':
        bot = context.bot_data.get('bot_instance')
        user_id = update.effective_user.id
        
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # End current challenge if exists
            cursor.execute('UPDATE challenges SET status = "completed" WHERE status IN ("active", "upcoming", "grace_period")')
            
            # Create new challenge with upcoming status
            cursor.execute('''
                INSERT INTO challenges (description, scoring_system, challenge_type, type_description, start_date, end_date, status, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                context.user_data['challenge_desc'],
                context.user_data['challenge_scoring'],
                context.user_data['challenge_type'],
                context.user_data['type_description'],
                context.user_data['start_date'],
                context.user_data['end_date'],
                'upcoming',
                user_id
            ))
            
            conn.commit()
            await update.message.reply_text("Challenge created successfully\\!", parse_mode='MarkdownV2')
            
        except sqlite3.Error as e:
            await update.message.reply_text("Error creating challenge\\. Please try again\\.", parse_mode='MarkdownV2')
            logger.error(f"Challenge creation error: {e}")
        finally:
            conn.close()
    
    elif response == 'n':
        await update.message.reply_text("Challenge creation cancelled\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return START_CHALLENGE_CONFIRM
    
    return ConversationHandler.END

async def start_challenge_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel challenge creation"""
    await update.message.reply_text("Challenge creation cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Add admin conversation
async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start add admin process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    bot = context.bot_data.get('bot_instance')
    if not bot.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is for admins only.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    await update.message.reply_text("Enter the Telegram username \(without @\) to make admin:", parse_mode='MarkdownV2')
    return ADD_ADMIN_USERNAME

async def add_admin_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin username input"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the username:", parse_mode='MarkdownV2')
        return ADD_ADMIN_USERNAME
    
    username = update.message.text.strip().lstrip('@')
    
    if not username:
        await update.message.reply_text("Username cannot be empty\\. Please enter a username:", parse_mode='MarkdownV2')
        return ADD_ADMIN_USERNAME
    
    if len(username) < 3 or len(username) > 32:
        await update.message.reply_text("Username must be between 3\\-32 characters\\. Please try again:", parse_mode='MarkdownV2')
        return ADD_ADMIN_USERNAME
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        await update.message.reply_text("Username can only contain letters, numbers, and underscores\\. Please try again:", parse_mode='MarkdownV2')
        return ADD_ADMIN_USERNAME
    
    context.user_data['admin_username'] = username
    
    await update.message.reply_text(
        f"Make @{escape_markdown_v2(username)} an admin?\n"
        f"Reply 'y' to confirm or 'n' to cancel\\.", parse_mode='MarkdownV2'
    )
    return ADD_ADMIN_CONFIRM

async def add_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm add admin"""
    response = update.message.text.strip().lower()
    
    if response == 'y':
        bot = context.bot_data.get('bot_instance')
        username = context.user_data['admin_username']
        adder_id = update.effective_user.id
        
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Find user by username
            cursor.execute('SELECT telegram_id FROM users WHERE username = ?', (username,))
            result = cursor.fetchone()
            
            if not result:
                await update.message.reply_text(f"User @{escape_markdown_v2(username)} not found\\. They need to interact with the bot first\\.", parse_mode='MarkdownV2')
                return ConversationHandler.END
            
            user_id = result[0]
            
            # Add as admin
            cursor.execute('''
                INSERT OR IGNORE INTO admins (user_id, added_by) 
                VALUES (?, ?)
            ''', (user_id, adder_id))
            
            if cursor.rowcount > 0:
                conn.commit()
                await update.message.reply_text(f"@{escape_markdown_v2(username)} is now an admin\\!", parse_mode='MarkdownV2')
            else:
                await update.message.reply_text(f"@{escape_markdown_v2(username)} is already an admin\\.", parse_mode='MarkdownV2')
            
        except sqlite3.Error as e:
            await update.message.reply_text("Error adding admin\\. Please try again\\.", parse_mode='MarkdownV2')
            logger.error(f"Add admin error: {e}")
        finally:
            conn.close()
    
    elif response == 'n':
        await update.message.reply_text("Add admin cancelled\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return ADD_ADMIN_CONFIRM
    
    return ConversationHandler.END

async def add_admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel add admin"""
    await update.message.reply_text("Add admin cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Remove admin conversation
async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start remove admin process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    bot = context.bot_data.get('bot_instance')
    if not bot.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is for admins only.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    await update.message.reply_text("Enter the Telegram username \(without @\) to remove as admin:", parse_mode='MarkdownV2')
    return REMOVE_ADMIN_USERNAME

async def remove_admin_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle remove admin username input"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the username:", parse_mode='MarkdownV2')
        return REMOVE_ADMIN_USERNAME
    
    username = update.message.text.strip().lstrip('@')
    
    if not username:
        await update.message.reply_text("Username cannot be empty\\. Please enter a username:", parse_mode='MarkdownV2')
        return REMOVE_ADMIN_USERNAME
    
    if len(username) < 3 or len(username) > 32:
        await update.message.reply_text("Username must be between 3\\-32 characters\\. Please try again:", parse_mode='MarkdownV2')
        return REMOVE_ADMIN_USERNAME
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        await update.message.reply_text("Username can only contain letters, numbers, and underscores\\. Please try again:", parse_mode='MarkdownV2')
        return REMOVE_ADMIN_USERNAME
    
    context.user_data['remove_admin_username'] = username
    
    await update.message.reply_text(
        f"Remove @{escape_markdown_v2(username)} as admin?\n"
        f"Reply 'y' to confirm or 'n' to cancel\\.", parse_mode='MarkdownV2'
    )
    return REMOVE_ADMIN_CONFIRM

async def remove_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm remove admin"""
    response = update.message.text.strip().lower()
    
    if response == 'y':
        bot = context.bot_data.get('bot_instance')
        username = context.user_data['remove_admin_username']
        
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Find user by username and remove admin status
            cursor.execute('''
                DELETE FROM admins 
                WHERE user_id = (SELECT telegram_id FROM users WHERE username = ?)
            ''', (username,))
            
            if cursor.rowcount > 0:
                conn.commit()
                await update.message.reply_text(f"@{escape_markdown_v2(username)} is no longer an admin\\.", parse_mode='MarkdownV2')
            else:
                await update.message.reply_text(f"@{escape_markdown_v2(username)} was not found as an admin\\.", parse_mode='MarkdownV2')
            
        except sqlite3.Error as e:
            await update.message.reply_text("Error removing admin\\. Please try again\\.", parse_mode='MarkdownV2')
            logger.error(f"Remove admin error: {e}")
        finally:
            conn.close()
    
    elif response == 'n':
        await update.message.reply_text("Remove admin cancelled\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return REMOVE_ADMIN_CONFIRM
    
    return ConversationHandler.END

async def remove_admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel remove admin"""
    await update.message.reply_text("Remove admin cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Remove entry conversation
async def remove_entry_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start remove entry process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    bot = context.bot_data.get('bot_instance')
    if not bot.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is for admins only.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    await update.message.reply_text("Enter the registered username to remove from competition:", parse_mode='MarkdownV2')
    return REMOVE_ENTRY_USERNAME

async def remove_entry_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle remove entry username input"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the username:", parse_mode='MarkdownV2')
        return REMOVE_ENTRY_USERNAME
    
    username = update.message.text.strip()
    
    if not username:
        await update.message.reply_text("Username cannot be empty\\. Please enter a username:", parse_mode='MarkdownV2')
        return REMOVE_ENTRY_USERNAME
    
    if len(username) < 3 or len(username) > 20:
        await update.message.reply_text("Username must be between 3\\-20 characters\\. Please try again:", parse_mode='MarkdownV2')
        return REMOVE_ENTRY_USERNAME
    
    context.user_data['remove_entry_username'] = username
    
    await update.message.reply_text(
        f"Remove all entries for '{escape_markdown_v2(username)}' from current competition?\n"
        f"Reply 'y' to confirm or 'n' to cancel\\.", parse_mode='MarkdownV2'
    )
    return REMOVE_ENTRY_CONFIRM

async def remove_entry_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm remove entry"""
    response = update.message.text.strip().lower()
    
    if response == 'y':
        bot = context.bot_data.get('bot_instance')
        username = context.user_data['remove_entry_username']
        
        current_challenge = bot.get_current_challenge()
        if not current_challenge:
            await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
            return ConversationHandler.END
        
        challenge_id = current_challenge[0]
        
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                DELETE FROM scores 
                WHERE challenge_id = ? AND user_id = (
                    SELECT telegram_id FROM users WHERE registered_username = ?
                )
            ''', (challenge_id, username))
            
            removed_count = cursor.rowcount
            conn.commit()
            
            if removed_count > 0:
                await update.message.reply_text(f"Removed {removed_count} entries for '{escape_markdown_v2(username)}'\\.", parse_mode='MarkdownV2')
            else:
                await update.message.reply_text(f"No entries found for '{escape_markdown_v2(username)}'\\.", parse_mode='MarkdownV2')
            
        except sqlite3.Error as e:
            await update.message.reply_text("Error removing entries\\. Please try again\\.", parse_mode='MarkdownV2')
            logger.error(f"Remove entry error: {e}")
        finally:
            conn.close()
    
    elif response == 'n':
        await update.message.reply_text("Remove entry cancelled\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return REMOVE_ENTRY_CONFIRM
    
    return ConversationHandler.END

async def remove_entry_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel remove entry"""
    await update.message.reply_text("Remove entry cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# New challenge suggestion conversation
async def new_challenge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start new challenge suggestion"""
    await update.message.reply_text("Enter challenge description \(verify it's unique before suggesting\):", parse_mode='MarkdownV2')
    return NEW_CHALLENGE_DESC

async def new_challenge_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle challenge description input"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the challenge description:", parse_mode='MarkdownV2')
        return NEW_CHALLENGE_DESC
    
    description = update.message.text.strip()
    
    if not description:
        await update.message.reply_text("Description cannot be empty\\. Please try again:", parse_mode='MarkdownV2')
        return NEW_CHALLENGE_DESC
    
    if len(description) < 10:
        await update.message.reply_text("Description should be at least 10 characters\\. Please try again:", parse_mode='MarkdownV2')
        return NEW_CHALLENGE_DESC
    
    if len(description) > 300:
        await update.message.reply_text("Description should be 300 characters or less\\. Please try again:", parse_mode='MarkdownV2')
        return NEW_CHALLENGE_DESC
    
    context.user_data['suggestion_desc'] = description
    await update.message.reply_text("Enter the scoring system:", parse_mode='MarkdownV2')
    return NEW_CHALLENGE_SCORING

async def new_challenge_scoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle scoring system input for suggestion"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the scoring system:", parse_mode='MarkdownV2')
        return NEW_CHALLENGE_SCORING
    
    scoring = update.message.text.strip()
    
    if not scoring:
        await update.message.reply_text("Scoring system cannot be empty\\. Please try again:", parse_mode='MarkdownV2')
        return NEW_CHALLENGE_SCORING
    
    if len(scoring) < 5:
        await update.message.reply_text("Scoring system should be at least 5 characters\\. Please try again:", parse_mode='MarkdownV2')
        return NEW_CHALLENGE_SCORING
    
    if len(scoring) > 150:
        await update.message.reply_text("Scoring system should be 150 characters or less\\. Please try again:", parse_mode='MarkdownV2')
        return NEW_CHALLENGE_SCORING
    
    context.user_data['suggestion_scoring'] = scoring
    
    desc = context.user_data['suggestion_desc']
    await update.message.reply_text(
        f"Submit this challenge suggestion?\n\n"
        f"**Description:** {escape_markdown_v2(desc)}\n"
        f"**Scoring:** {escape_markdown_v2(scoring)}\n\n"
        f"Reply 'y' to confirm or 'n' to cancel\\.", parse_mode='MarkdownV2'
    )
    return NEW_CHALLENGE_CONFIRM

async def new_challenge_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm new challenge suggestion"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return NEW_CHALLENGE_CONFIRM
    
    response = update.message.text.strip().lower()
    
    if response == 'y':
        bot = context.bot_data.get('bot_instance')
        user_id = update.effective_user.id
        
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check how many suggestions user has
            cursor.execute('''
                SELECT COUNT(*) FROM challenge_suggestions WHERE suggested_by = ?
            ''', (user_id,))
            count = cursor.fetchone()[0]
            
            if count >= 3:
                await update.message.reply_text("You can only have a maximum of 3 suggestions\\.", parse_mode='MarkdownV2')
                return ConversationHandler.END
            
            # Add suggestion
            cursor.execute('''
                INSERT INTO challenge_suggestions (suggested_by, description, scoring_system)
                VALUES (?, ?, ?)
            ''', (user_id, context.user_data['suggestion_desc'], context.user_data['suggestion_scoring']))
            
            conn.commit()
            await update.message.reply_text("Challenge suggestion submitted\\!", parse_mode='MarkdownV2')
            
        except sqlite3.Error as e:
            await update.message.reply_text("Error submitting suggestion\\. Please try again\\.", parse_mode='MarkdownV2')
            logger.error(f"Challenge suggestion error: {e}")
        finally:
            conn.close()
    
    elif response == 'n':
        await update.message.reply_text("Challenge suggestion cancelled\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return NEW_CHALLENGE_CONFIRM
    
    return ConversationHandler.END

async def new_challenge_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel new challenge suggestion"""
    await update.message.reply_text("Challenge suggestion cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Edit challenge conversation
async def edit_challenge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start edit challenge process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    bot = context.bot_data.get('bot_instance')
    if not bot.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is for admins only.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, description, start_date, end_date, status
        FROM challenges
        ORDER BY created_at DESC
        LIMIT 10
    ''')
    challenges = cursor.fetchall()
    conn.close()
    
    if not challenges:
        await update.message.reply_text("No challenges found\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    message = "📝 **Select Challenge to Edit** 📝\n\n"
    for i, (challenge_id, description, start_date, end_date, status) in enumerate(challenges, 1):
        # Convert dates to dd,mm,yyyy format
        try:
            start_formatted = datetime.strptime(str(start_date), '%Y-%m-%d').strftime('%d/%m/%Y')
            end_formatted = datetime.strptime(str(end_date), '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            start_formatted = str(start_date)
            end_formatted = str(end_date)
        
        message += f"{i}\\. {escape_markdown_v2(description[:50])}\n"
        message += f"   Period: {escape_markdown_v2(start_formatted)} to {escape_markdown_v2(end_formatted)}\n"
        message += f"   Status: {escape_markdown_v2(status)}\n\n"
    
    message += "Reply with a number to select the challenge to edit:"
    await update.message.reply_text(message, parse_mode='MarkdownV2')
    return EDIT_CHALLENGE_SELECT

async def edit_challenge_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle challenge selection for editing"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a number to select a challenge:", parse_mode='MarkdownV2')
        return EDIT_CHALLENGE_SELECT
    
    try:
        selection = int(update.message.text.strip())
        
        bot = context.bot_data.get('bot_instance')
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, description, scoring_system, start_date, end_date, status
            FROM challenges
            ORDER BY created_at DESC
            LIMIT 10
        ''')
        challenges = cursor.fetchall()
        conn.close()
        
        if selection < 1 or selection > len(challenges):
            await update.message.reply_text("Invalid selection\\. Please choose a valid number:", parse_mode='MarkdownV2')
            return EDIT_CHALLENGE_SELECT
        
        challenge = challenges[selection - 1]
        context.user_data['edit_challenge_id'] = challenge[0]
        context.user_data['edit_challenge_data'] = challenge
        
        # Convert dates to dd,mm,yyyy format for display
        try:
            start_formatted = datetime.strptime(str(challenge[3]), '%Y-%m-%d').strftime('%d/%m/%Y')
            end_formatted = datetime.strptime(str(challenge[4]), '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            start_formatted = str(challenge[3])
            end_formatted = str(challenge[4])
        
        message = f"📝 **Editing Challenge** 📝\n\n"
        message += f"**Current details:**\n"
        message += f"1\\. Description: {escape_markdown_v2(challenge[1])}\n"
        message += f"2\\. Scoring: {escape_markdown_v2(challenge[2])}\n"
        message += f"3\\. Start Date: {escape_markdown_v2(start_formatted)}\n"
        message += f"4\\. End Date: {escape_markdown_v2(end_formatted)}\n"
        message += f"5\\. Status: {escape_markdown_v2(challenge[5])}\n\n"
        message += "Reply with a number to select what to edit:"
        
        await update.message.reply_text(message, parse_mode='MarkdownV2')
        return EDIT_CHALLENGE_FIELD
        
    except ValueError:
        await update.message.reply_text("Please enter a valid number:", parse_mode='MarkdownV2')
        return EDIT_CHALLENGE_SELECT

async def edit_challenge_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle field selection for editing"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a number to select a field:", parse_mode='MarkdownV2')
        return EDIT_CHALLENGE_FIELD
    
    try:
        field_num = int(update.message.text.strip())
        
        if field_num < 1 or field_num > 5:
            await update.message.reply_text("Invalid selection\\. Please choose 1\\-5:", parse_mode='MarkdownV2')
            return EDIT_CHALLENGE_FIELD
        
        context.user_data['edit_field'] = field_num
        
        field_names = {
            1: "description",
            2: "scoring system",
            3: "start date",
            4: "end date",
            5: "status"
        }
        
        field_name = field_names[field_num]
        
        if field_num in [3, 4]:  # Date fields
            await update.message.reply_text(f"Enter new {field_name} \(format: dd,mm,yyyy\):", parse_mode='MarkdownV2')
        elif field_num == 5:  # Status field
            await update.message.reply_text(
                "Enter new status:\n"
                "• active\n"
                "• upcoming\n" 
                "• completed\n"
                "• cancelled", parse_mode='MarkdownV2'
            )
        else:
            await update.message.reply_text(f"Enter new {field_name}:", parse_mode='MarkdownV2')
        
        return EDIT_CHALLENGE_VALUE
        
    except ValueError:
        await update.message.reply_text("Please enter a valid number:", parse_mode='MarkdownV2')
        return EDIT_CHALLENGE_FIELD

async def edit_challenge_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new value input for editing"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with the new value:", parse_mode='MarkdownV2')
        return EDIT_CHALLENGE_VALUE
    
    new_value = update.message.text.strip()
    field_num = context.user_data.get('edit_field')
    
    if not new_value:
        await update.message.reply_text("Value cannot be empty\\. Please try again:", parse_mode='MarkdownV2')
        return EDIT_CHALLENGE_VALUE
    
    # Validate based on field type
    if field_num in [3, 4]:  # Date fields
        try:
            datetime.strptime(new_value, '%d/%m/%Y')
        except ValueError:
            await update.message.reply_text("Invalid date format\\. Please use dd,mm,yyyy:", parse_mode='MarkdownV2')
            return EDIT_CHALLENGE_VALUE
    
    elif field_num == 5:  # Status field
        valid_statuses = ['active', 'upcoming', 'completed', 'cancelled']
        if new_value.lower() not in valid_statuses:
            await update.message.reply_text("Invalid status\\. Please use: active, upcoming, completed, or cancelled:", parse_mode='MarkdownV2')
            return EDIT_CHALLENGE_VALUE
        new_value = new_value.lower()
    
    context.user_data['new_value'] = new_value
    
    field_names = {
        1: "description",
        2: "scoring system", 
        3: "start date",
        4: "end date",
        5: "status"
    }
    
    field_name = field_names[field_num]
    
    message = f"📝 **Confirm Edit** 📝\n\n"
    message += f"**Field:** {field_name}\n"
    message += f"**New value:** {escape_markdown_v2(new_value)}\n\n"
    message += "Reply 'y' to confirm or 'n' to cancel\\."
    
    await update.message.reply_text(message, parse_mode='MarkdownV2')
    return EDIT_CHALLENGE_CONFIRM

async def edit_challenge_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm challenge edit"""
    response = update.message.text.strip().lower()
    
    if response == 'y':
        bot = context.bot_data.get('bot_instance')
        challenge_id = context.user_data.get('edit_challenge_id')
        field_num = context.user_data.get('edit_field')
        new_value = context.user_data.get('new_value')
        
        field_columns = {
            1: "description",
            2: "scoring_system",
            3: "start_date",
            4: "end_date", 
            5: "status"
        }
        
        column = field_columns[field_num]
        
        # Convert date format for database if needed
        if field_num in [3, 4]:
            try:
                date_obj = datetime.strptime(new_value, '%d/%m/%Y')
                new_value = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                await update.message.reply_text("Date conversion error\\.", parse_mode='MarkdownV2')
                return ConversationHandler.END
        
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(f'UPDATE challenges SET {column} = ? WHERE id = ?', (new_value, challenge_id))
            conn.commit()
            await update.message.reply_text("✅ Challenge updated successfully\\!", parse_mode='MarkdownV2')
        except Exception as e:
            logger.error(f"Error updating challenge: {e}")
            await update.message.reply_text("❌ Error updating challenge\\.", parse_mode='MarkdownV2')
        finally:
            conn.close()
    
    elif response == 'n':
        await update.message.reply_text("Edit cancelled\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return EDIT_CHALLENGE_CONFIRM
    
    return ConversationHandler.END

async def edit_challenge_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel challenge editing"""
    await update.message.reply_text("Challenge editing cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Remove challenge conversation
async def remove_challenge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start remove challenge process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    bot = context.bot_data.get('bot_instance')
    if not bot.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is for admins only.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, description, start_date, end_date, status
        FROM challenges
        ORDER BY created_at DESC
        LIMIT 10
    ''')
    challenges = cursor.fetchall()
    conn.close()
    
    if not challenges:
        await update.message.reply_text("No challenges found\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    message = "🗑️ **Select Challenge to Remove** 🗑️\n\n"
    message += "⚠️ **WARNING:** Removing a challenge will delete all related data including scores and votes\\!\n\n"
    
    for i, (challenge_id, description, start_date, end_date, status) in enumerate(challenges, 1):
        # Convert dates to dd,mm,yyyy format
        try:
            start_formatted = datetime.strptime(str(start_date), '%Y-%m-%d').strftime('%d/%m/%Y')
            end_formatted = datetime.strptime(str(end_date), '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            start_formatted = str(start_date)
            end_formatted = str(end_date)
        
        message += f"{i}\\. {escape_markdown_v2(description[:50])}\n"
        message += f"   Period: {escape_markdown_v2(start_formatted)} to {escape_markdown_v2(end_formatted)}\n"
        message += f"   Status: {escape_markdown_v2(status)}\n\n"
    
    message += "Reply with a number to select the challenge to remove:"
    await update.message.reply_text(message, parse_mode='MarkdownV2')
    return REMOVE_CHALLENGE_SELECT

async def remove_challenge_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle challenge selection for removal"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a number to select a challenge:", parse_mode='MarkdownV2')
        return REMOVE_CHALLENGE_SELECT
    
    try:
        selection = int(update.message.text.strip())
        
        bot = context.bot_data.get('bot_instance')
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, description, start_date, end_date, status
            FROM challenges
            ORDER BY created_at DESC
            LIMIT 10
        ''')
        challenges = cursor.fetchall()
        conn.close()
        
        if selection < 1 or selection > len(challenges):
            await update.message.reply_text("Invalid selection\\. Please choose a valid number:", parse_mode='MarkdownV2')
            return REMOVE_CHALLENGE_SELECT
        
        challenge = challenges[selection - 1]
        context.user_data['remove_challenge_id'] = challenge[0]
        context.user_data['remove_challenge_data'] = challenge
        
        # Convert dates to dd,mm,yyyy format for display
        try:
            start_formatted = datetime.strptime(str(challenge[2]), '%Y-%m-%d').strftime('%d/%m/%Y')
            end_formatted = datetime.strptime(str(challenge[3]), '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            start_formatted = str(challenge[2])
            end_formatted = str(challenge[3])
        
        message = f"🗑️ **Confirm Challenge Removal** 🗑️\n\n"
        message += f"**Challenge:** {escape_markdown_v2(challenge[1])}\n"
        message += f"**Period:** {escape_markdown_v2(start_formatted)} to {escape_markdown_v2(end_formatted)}\n"
        message += f"**Status:** {escape_markdown_v2(challenge[4])}\n\n"
        message += f"⚠️ **WARNING:** This will permanently delete:\n"
        message += f"• The challenge itself\n"
        message += f"• All scores for this challenge\n"
        message += f"• All baseline/current values for this challenge\n"
        message += f"• All related notifications\n\n"
        message += f"Reply 'y' to confirm removal or 'n' to cancel\\."
        
        await update.message.reply_text(message, parse_mode='MarkdownV2')
        return REMOVE_CHALLENGE_CONFIRM
        
    except ValueError:
        await update.message.reply_text("Please enter a valid number:", parse_mode='MarkdownV2')
        return REMOVE_CHALLENGE_SELECT

async def remove_challenge_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm challenge removal"""
    response = update.message.text.strip().lower()
    
    if response == 'y':
        bot = context.bot_data.get('bot_instance')
        challenge_id = context.user_data.get('remove_challenge_id')
        challenge_data = context.user_data.get('remove_challenge_data')
        
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Delete in order to respect foreign key constraints
            cursor.execute('DELETE FROM scores WHERE challenge_id = ?', (challenge_id,))
            cursor.execute('DELETE FROM baseline_values WHERE challenge_id = ?', (challenge_id,))
            cursor.execute('DELETE FROM challenge_notifications WHERE challenge_id = ?', (challenge_id,))
            cursor.execute('DELETE FROM challenges WHERE id = ?', (challenge_id,))
            
            conn.commit()
            
            await update.message.reply_text(
                f"✅ Challenge '{escape_markdown_v2(challenge_data[1][:50])}' has been permanently removed\\!",
                parse_mode='MarkdownV2'
            )
        except Exception as e:
            logger.error(f"Error removing challenge: {e}")
            await update.message.reply_text("❌ Error removing challenge\\.", parse_mode='MarkdownV2')
        finally:
            conn.close()
    
    elif response == 'n':
        await update.message.reply_text("Challenge removal cancelled\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply 'y' to confirm or 'n' to cancel:", parse_mode='MarkdownV2')
        return REMOVE_CHALLENGE_CONFIRM
    
    return ConversationHandler.END

async def remove_challenge_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel challenge removal"""
    await update.message.reply_text("Challenge removal cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

async def admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List current admins"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return
    
    bot = context.bot_data.get('bot_instance')
    if not bot.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is for admins only.", parse_mode='MarkdownV2')
        return
    
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.registered_username, u.username, a.added_date
        FROM admins a
        JOIN users u ON a.user_id = u.telegram_id
        ORDER BY a.added_date
    ''')
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        await update.message.reply_text("No admins found\\.", parse_mode='MarkdownV2')
        return
    
    admin_list = "👑 **Current Admins** 👑\n\n"
    for reg_username, tg_username, added_date in results:
        display_name = escape_markdown_v2(reg_username or tg_username or "Unknown")
        # Convert YYYY-MM-DD to dd,mm,yyyy format
        try:
            date_obj = datetime.strptime(added_date[:10], '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d/%m/%Y')
        except:
            formatted_date = added_date[:10]  # fallback to original if parsing fails
        admin_list += f"• {display_name} \(Added: {escape_markdown_v2(formatted_date)}\)\n"
    
    await update.message.reply_text(admin_list, parse_mode='MarkdownV2')

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    await update.message.reply_text("Current operation cancelled\\.", parse_mode='MarkdownV2')

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send anonymous feedback"""
    if not context.args:
        await update.message.reply_text("Please provide feedback: /feedback <your feedback>", parse_mode='MarkdownV2')
        return
    
    feedback_text = ' '.join(context.args)
    
    # Get user info
    user = update.effective_user
    username = user.username or "No username"
    user_id = user.id
    
    # Store feedback in database (user info for moderation only, not displayed)
    bot = context.bot_data.get('bot_instance')
    if bot:
        try:
            conn = bot.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO feedback (user_id, username, feedback_text)
                VALUES (?, ?, ?)
            ''', (user_id, username, feedback_text))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Anonymous feedback submitted (ID: {user_id}): {feedback_text}")
        except Exception as e:
            logger.error(f"Failed to store feedback in database: {e}")
    
    await update.message.reply_text(
        "Thank you for your feedback\\! It has been sent anonymously to the developer\\.",
        parse_mode='MarkdownV2'
    )

async def show_feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start showing feedback with pagination (admin only)"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    bot = context.bot_data.get('bot_instance')
    if not bot or not bot.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is for admins only.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    # Initialize pagination
    context.user_data['feedback_offset'] = 0
    
    # Show first 10 feedback entries
    return await show_feedback_page(update, context)

async def show_feedback_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a page of feedback entries"""
    bot = context.bot_data.get('bot_instance')
    offset = context.user_data.get('feedback_offset', 0)
    
    try:
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        # Get 11 entries to check if there are more
        cursor.execute('''
            SELECT id, user_id, username, feedback_text, submitted_date
            FROM feedback
            ORDER BY submitted_date DESC
            LIMIT 11 OFFSET ?
        ''', (offset,))
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            if offset == 0:
                await update.message.reply_text("No feedback found\\.", parse_mode='MarkdownV2')
            else:
                await update.message.reply_text("No more feedback to show\\.", parse_mode='MarkdownV2')
            return ConversationHandler.END
        
        # Show only first 10, check if there's an 11th for "next" option
        display_results = results[:10]
        has_more = len(results) > 10
        
        page_num = (offset // 10) + 1
        feedback_list = f"📝 *Feedback Page {page_num}*\n\n"
        
        for feedback_id, user_id, username, feedback_text, submitted_date in display_results:
            # Format the date
            try:
                date_obj = datetime.fromisoformat(submitted_date.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime('%d/%m/%Y %H:%M')
            except:
                formatted_date = submitted_date[:16]  # fallback
            
            # Escape the feedback text for MarkdownV2
            escaped_feedback = escape_markdown_v2(feedback_text)
            escaped_date = escape_markdown_v2(formatted_date)
            
            feedback_list += f"**\\#{feedback_id}** \\| {escaped_date}\n"
            feedback_list += f"_{escaped_feedback}_\n\n"
        
        # Add navigation instructions
        if has_more:
            feedback_list += "Type 'next' for more feedback or /cancel to stop\\."
        else:
            feedback_list += "No more feedback\\. Type /cancel to stop\\."
        
        await update.message.reply_text(feedback_list, parse_mode='MarkdownV2')
        
        if has_more:
            return FEEDBACK_VIEWING
        else:
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error retrieving feedback: {e}")
        await update.message.reply_text("Error retrieving feedback\\. Please try again\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END

async def show_feedback_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle next page request"""
    message_text = update.message.text.lower().strip()
    
    if message_text == 'next':
        # Move to next page
        context.user_data['feedback_offset'] = context.user_data.get('feedback_offset', 0) + 10
        return await show_feedback_page(update, context)
    else:
        await update.message.reply_text("Type 'next' for more feedback or /cancel to stop\\.", parse_mode='MarkdownV2')
        return FEEDBACK_VIEWING

async def show_feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel feedback viewing"""
    await update.message.reply_text("Feedback viewing cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Challenge commands
async def challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current challenge info"""
    bot = context.bot_data.get('bot_instance')
    current_challenge = bot.get_current_challenge()
    
    if not current_challenge:
        await update.message.reply_text("No active challenge currently\\.", parse_mode='MarkdownV2')
        return
    
    # Debug: Log the actual length and content
    logger.info(f"Challenge data length: {len(current_challenge)}, data: {current_challenge}")
    
    # Unpack only the values we actually have
    if len(current_challenge) == 8:
        # Handle 8-column case
        _, description, scoring_system, start_date, end_date, _, _, _ = current_challenge
    else:
        # Handle 10-column case - actual order from database after migration
        _, description, scoring_system, start_date, end_date, _, _, _, _, _ = current_challenge
    
    # Get actual dynamic status
    actual_status, status_message = bot.get_challenge_status(current_challenge)
    
    # Convert dates to dd,mm,yyyy format
    try:
        start_formatted = datetime.strptime(str(start_date), '%Y-%m-%d').strftime('%d/%m/%Y')
        end_formatted = datetime.strptime(str(end_date), '%Y-%m-%d').strftime('%d/%m/%Y')
    except:
        start_formatted = str(start_date)
        end_formatted = str(end_date)
    
    challenge_info = f"🎯 _*Current Challenge*_ 🎯\n\n"
    challenge_info += f"_*Description:*_\n\n{escape_markdown_v2(description)}\n\n"
    challenge_info += f"_*Scoring:*_ {escape_markdown_v2(scoring_system)}\n"
    challenge_info += f"_*Period:*_ {escape_markdown_v2(start_formatted)} to {escape_markdown_v2(end_formatted)}\n"
    challenge_info += f"_*Status:*_ {status_message}"

    await update.message.reply_text(challenge_info, parse_mode='MarkdownV2')

async def next_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show and vote on next challenge suggestions"""
    bot = context.bot_data.get('bot_instance')
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, description, scoring_system, votes
        FROM challenge_suggestions
        ORDER BY votes DESC, created_at ASC
    ''')
    
    suggestions = cursor.fetchall()
    conn.close()
    
    if not suggestions:
        await update.message.reply_text(
            "No challenge suggestions yet\\.\n"
            "Reply with 'new' to suggest a new challenge\\.", parse_mode='MarkdownV2'
        )
        return
    
    message = "🗳️ **Next Challenge Suggestions** 🗳️\n\n"
    for i, (suggestion_id, description, scoring, votes) in enumerate(suggestions, 1):
        message += f"{i}\\. {escape_markdown_v2(description)}\n"
        message += f"   Scoring: {escape_markdown_v2(scoring)}\n"
        message += f"   Votes: {votes}\n\n"
    
    message += "Reply with a number to vote, or 'new' to suggest a new challenge\\."
    await update.message.reply_text(message, parse_mode='MarkdownV2')

async def handle_vote_or_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voting on challenges or starting new suggestions"""
    if update.effective_chat.type == 'private':
        return  # Only handle in groups
    
    message_text = update.message.text.strip()
    
    # Check if it's a number (vote)
    try:
        vote_num = int(message_text)
        await handle_challenge_vote(update, context, vote_num)
        return
    except ValueError:
        pass
    
    # Check if it's "new" for new suggestion
    if message_text.lower() == 'new':
        await update.message.reply_text("Please send me a private message to suggest a new challenge using /newsuggest", parse_mode='MarkdownV2')
        return

async def handle_challenge_vote(update: Update, context: ContextTypes.DEFAULT_TYPE, vote_num: int):
    """Handle voting on a specific challenge"""
    bot = context.bot_data.get('bot_instance')
    user_id = update.effective_user.id
    
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get all suggestions ordered by votes and creation
        cursor.execute('''
            SELECT id FROM challenge_suggestions
            ORDER BY votes DESC, created_at ASC
        ''')
        suggestions = cursor.fetchall()
        
        if vote_num < 1 or vote_num > len(suggestions):
            await update.message.reply_text("Invalid vote number\\.", parse_mode='MarkdownV2')
            return
        
        suggestion_id = suggestions[vote_num - 1][0]
        
        # Check if user already voted for this suggestion
        cursor.execute('''
            SELECT 1 FROM votes WHERE user_id = ? AND suggestion_id = ?
        ''', (user_id, suggestion_id))
        
        if cursor.fetchone():
            await update.message.reply_text("You've already voted for this challenge\\.", parse_mode='MarkdownV2')
            return
        
        # Add vote
        cursor.execute('''
            INSERT INTO votes (user_id, suggestion_id) VALUES (?, ?)
        ''', (user_id, suggestion_id))
        
        # Update vote count
        cursor.execute('''
            UPDATE challenge_suggestions 
            SET votes = votes + 1 
            WHERE id = ?
        ''', (suggestion_id,))
        
        conn.commit()
        await update.message.reply_text("Vote recorded\\! 🗳️", parse_mode='MarkdownV2')
        
    except sqlite3.Error as e:
        await update.message.reply_text("Error recording vote\\.", parse_mode='MarkdownV2')
        logger.error(f"Vote error: {e}")
    finally:
        conn.close()

async def handle_past_challenge_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle selection of past challenge to view"""
    if update.effective_chat.type == 'private':
        return
    
    message_text = update.message.text.strip()
    
    try:
        challenge_num = int(message_text)
        bot = context.bot_data.get('bot_instance')
        
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        # Get past challenges
        cursor.execute('''
            SELECT id, description, start_date, end_date, challenge_type
            FROM challenges
            WHERE status = 'completed'
            ORDER BY end_date DESC
            LIMIT 10
        ''')
        
        past_challenges = cursor.fetchall()
        
        if challenge_num < 1 or challenge_num > len(past_challenges):
            return  # Invalid number, ignore
        
        challenge_id, description, start_date, end_date, challenge_type = past_challenges[challenge_num - 1]
        
        if challenge_type == 'change':
            # For change challenges, get top performers by absolute change
            cursor.execute('''
                SELECT 
                    u.registered_username, 
                    ((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100 as percent_change
                FROM baseline_values b
                JOIN users u ON b.user_id = u.telegram_id
                WHERE b.challenge_id = ? AND b.baseline_value != 0
                ORDER BY ABS(((b.current_value - b.baseline_value) / ABS(b.baseline_value)) * 100) DESC
                LIMIT 20
            ''', (challenge_id,))
            results = cursor.fetchall()
        else:
            # For points challenges, get top scorers
            cursor.execute('''
                SELECT u.registered_username, SUM(s.points) as total_points
                FROM scores s
                JOIN users u ON s.user_id = u.telegram_id
                WHERE s.challenge_id = ?
                GROUP BY s.user_id, u.registered_username
                ORDER BY total_points DESC
                LIMIT 20
            ''', (challenge_id,))
            results = cursor.fetchall()
            
        conn.close()
        
        if not results:
            await update.message.reply_text("No results found for this challenge\\.", parse_mode='MarkdownV2')
            return
        
        # Convert dates to dd,mm,yyyy format
        try:
            start_formatted = datetime.strptime(str(start_date), '%Y-%m-%d').strftime('%d/%m/%Y')
            end_formatted = datetime.strptime(str(end_date), '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            start_formatted = str(start_date)
            end_formatted = str(end_date)
        
        result_text = f"🏆 **{escape_markdown_v2(description)}** 🏆\n"
        result_text += f"Period: {escape_markdown_v2(start_formatted)} to {escape_markdown_v2(end_formatted)}\n\n"
        result_text += "**Final Results:**\n"
        
        for i, entry in enumerate(results, 1):
            username = entry[0]
            value = entry[1]
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}\\."
            
            if challenge_type == 'change':
                change_sign = "\+" if value >= 0 else ""
                result_text += f"{medal} {escape_markdown_v2(username)}: {change_sign}{value:.2f}%\n"
            else:
                result_text += f"{medal} {escape_markdown_v2(username)}: {value:,} points\n"
        
        await update.message.reply_text(result_text, parse_mode='MarkdownV2')
        
    except (ValueError, IndexError):
        pass  # Not a valid number, ignore

async def past_challenges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show past challenges"""
    bot = context.bot_data.get('bot_instance')
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, description, start_date, end_date
        FROM challenges
        WHERE status = 'completed'
        ORDER BY end_date DESC
        LIMIT 10
    ''')
    
    past_challenges = cursor.fetchall()
    conn.close()
    
    if not past_challenges:
        await update.message.reply_text("No past challenges exist\\.", parse_mode='MarkdownV2')
        return
    
    message = "📚 **Past Challenges** 📚\n\n"
    for i, (challenge_id, description, start_date, end_date) in enumerate(past_challenges, 1):
        # Convert dates to dd,mm,yyyy format
        try:
            start_formatted = datetime.strptime(str(start_date), '%Y-%m-%d').strftime('%d/%m/%Y')
            end_formatted = datetime.strptime(str(end_date), '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            start_formatted = str(start_date)
            end_formatted = str(end_date)
        
        message += f"{i}\\. {escape_markdown_v2(description)}\n"
        message += f"   Period: {escape_markdown_v2(start_formatted)} to {escape_markdown_v2(end_formatted)}\n\n"
    
    message += "Reply with a number to view final results\\."
    await update.message.reply_text(message, parse_mode='MarkdownV2')

# Baseline value management for change challenges
async def setbaseline_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start baseline value setting process"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    bot = context.bot_data.get('bot_instance')
    current_challenge = bot.get_current_challenge()
    
    if not current_challenge:
        await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    # Check if it's a change challenge
    if len(current_challenge) > 3 and current_challenge[3] != 'change': # challenge[3] is challenge_type
        await update.message.reply_text("This command is only for change\\-based challenges\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    challenge_id = current_challenge[0]
    challenge_desc = current_challenge[1]
    scoring_desc = current_challenge[2]
    
    await update.message.reply_text(
        f"📊 **Setting Baseline Value** 📊\n\n"
        f"**Challenge:** {escape_markdown_v2(challenge_desc)}\n"
        f"**Measuring:** {escape_markdown_v2(scoring_desc)}\n\n"
        f"Enter your starting value \(numbers only, e\\.g\\., '75\\.5', '8500'\):", parse_mode='MarkdownV2'
    )
    
    context.user_data['baseline_challenge_id'] = challenge_id
    return BASELINE_VALUE

async def setbaseline_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle baseline value input"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with your baseline value:", parse_mode='MarkdownV2')
        return BASELINE_VALUE
    
    value_str = update.message.text.strip()
    
    if not value_str:
        await update.message.reply_text("Please enter a number for your baseline value:", parse_mode='MarkdownV2')
        return BASELINE_VALUE
    
    try:
        value = float(value_str)
        
        # Reasonable bounds check
        if abs(value) > 1000000:
            await update.message.reply_text("Value seems too large\\. Please enter a reasonable number:", parse_mode='MarkdownV2')
            return BASELINE_VALUE
        
        user_id = update.effective_user.id
        challenge_id = context.user_data.get('baseline_challenge_id')
        
        if not challenge_id:
            await update.message.reply_text("Session expired\\. Please start over with /setbaseline", parse_mode='MarkdownV2')
            return ConversationHandler.END
        
        bot = context.bot_data.get('bot_instance')
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        # Insert or update baseline value
        cursor.execute('''
            INSERT OR REPLACE INTO baseline_values (user_id, challenge_id, baseline_value, current_value)
            VALUES (?, ?, ?, ?)
        ''', (user_id, challenge_id, value, value))
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Baseline value set to {value}\!", parse_mode='MarkdownV2')
        
    except ValueError:
        await update.message.reply_text("Please enter a valid number \(e\\.g\\., '75\\.5', '8500'\):", parse_mode='MarkdownV2')
        return BASELINE_VALUE
    except Exception as e:
        logger.error(f"Error in setbaseline_value: {e}")
        await update.message.reply_text("An error occurred\\. Please try again or contact an admin\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    return ConversationHandler.END

async def setbaseline_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel baseline setting"""
    await update.message.reply_text("Baseline setting cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

# Update value for change challenges
async def updatevalue_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start value update process for change challenges"""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    bot = context.bot_data.get('bot_instance')
    current_challenge = bot.get_current_challenge()
    
    if not current_challenge:
        await update.message.reply_text("No active challenge found\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    # Check if it's a change challenge
    if len(current_challenge) > 3 and current_challenge[3] != 'change': # challenge[3] is challenge_type
        await update.message.reply_text("This command is only for change\\-based challenges\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    challenge_id = current_challenge[0]
    user_id = update.effective_user.id
    
    # Check if user has baseline
    conn = bot.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT baseline_value, current_value FROM baseline_values WHERE user_id = ? AND challenge_id = ?', 
                   (user_id, challenge_id))
    baseline_data = cursor.fetchone()
    conn.close()
    
    if not baseline_data:
        await update.message.reply_text(
            "❌ You need to set your baseline value first\\!\n"
            "Use /setbaseline to set your starting value\\.", parse_mode='MarkdownV2'
        )
        return ConversationHandler.END
    
    baseline_value, current_value = baseline_data
    
    await update.message.reply_text(
        f"📊 **Update Your Value** 📊\n\n"
        f"**Baseline:** {baseline_value}\n"
        f"**Current:** {current_value}\n\n"
        f"Enter your new value:", parse_mode='MarkdownV2'
    )
    
    context.user_data['update_challenge_id'] = challenge_id
    context.user_data['baseline_value'] = baseline_value
    return UPDATE_VALUE

async def updatevalue_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle value update input"""
    if not update.message or not update.message.text:
        await update.message.reply_text("Please send a text message with your new value:", parse_mode='MarkdownV2')
        return UPDATE_VALUE
    
    value_str = update.message.text.strip()
    
    if not value_str:
        await update.message.reply_text("Please enter a number for your new value:", parse_mode='MarkdownV2')
        return UPDATE_VALUE
    
    try:
        new_value = float(value_str)
        
        # Reasonable bounds check
        if abs(new_value) > 1000000:
            await update.message.reply_text("Value seems too large\\. Please enter a reasonable number:", parse_mode='MarkdownV2')
            return UPDATE_VALUE
        
        user_id = update.effective_user.id
        challenge_id = context.user_data.get('update_challenge_id')
        baseline_value = context.user_data.get('baseline_value')
        
        if not challenge_id or baseline_value is None:
            await update.message.reply_text("Session expired\\. Please start over with /updatevalue", parse_mode='MarkdownV2')
            return ConversationHandler.END
        
        # Calculate percentage change
        if baseline_value != 0:
            percent_change = ((new_value - baseline_value) / abs(baseline_value)) * 100
        else:
            percent_change = 0
        
        bot = context.bot_data.get('bot_instance')
        conn = bot.get_db_connection()
        cursor = conn.cursor()
        
        # Update current value
        cursor.execute('''
            UPDATE baseline_values 
            SET current_value = ?, last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ? AND challenge_id = ?
        ''', (new_value, user_id, challenge_id))
        
        conn.commit()
        conn.close()
        
        # Format change display
        change_sign = "\+" if percent_change >= 0 else ""
        await update.message.reply_text(
            f"✅ Value updated\\!\n\n"
            f"**Previous:** {baseline_value}\n"
            f"**New:** {new_value}\n"
            f"**Change:** {change_sign}{percent_change:.2f}%", parse_mode='MarkdownV2'
        )
        
    except ValueError:
        await update.message.reply_text("Please enter a valid number:", parse_mode='MarkdownV2')
        return UPDATE_VALUE
    except Exception as e:
        logger.error(f"Error in updatevalue_value: {e}")
        await update.message.reply_text("An error occurred\\. Please try again or contact an admin\\.", parse_mode='MarkdownV2')
        return ConversationHandler.END
    
    return ConversationHandler.END

async def updatevalue_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel value update"""
    await update.message.reply_text("Value update cancelled\\.", parse_mode='MarkdownV2')
    return ConversationHandler.END

def get_finnish_time():
    """Get current time in Finnish timezone (UTC+2/UTC+3)"""
    # Simple approach: UTC+2 (summer time) or UTC+3 (winter time)
    # For exact DST handling, you'd need a proper timezone library
    import datetime as dt
    utc_now = datetime.now(dt.timezone.utc)
    # Assuming UTC+2 for simplicity - in production use proper timezone handling
    finnish_time = utc_now + timedelta(hours=2)
    return finnish_time

async def check_challenge_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Check and send challenge notifications at specific Finnish times"""
    bot_instance = context.bot_data.get('bot_instance')
    if bot_instance:
        finnish_time = get_finnish_time()
        logger.info(f"Running notification check at Finnish time: {finnish_time.strftime('%H:%M')}")
        await bot_instance.check_and_send_notifications(context.application)

def main():
    """Main function to run the bot"""
    # Get your bot token from @BotFather on Telegram
    # Instructions: https://core.telegram.org/bots#6-botfather
    TOKEN = "7954500541:AAFjO4FDF977AZTst6rCP38FNEgUciCRxwM"  # Replace this with your actual token
    
    bot_instance = CompetitionBot(TOKEN)
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Store bot instance in context
    application.bot_data['bot_instance'] = bot_instance
    
    # Add conversation handlers
    register_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={
            REGISTER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_username)],
        },
        fallbacks=[CommandHandler('cancel', register_cancel)],
        per_chat=True
    )
    
    add_score_handler = ConversationHandler(
        entry_points=[CommandHandler('addscore', add_score_start)],
        states={
            ADD_SCORE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_score_date)],
            ADD_SCORE_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_score_points)],
            ADD_SCORE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_score_confirm)],
        },
        fallbacks=[CommandHandler('cancel', add_score_cancel)],
        per_chat=True
    )
    
    remove_score_handler = ConversationHandler(
        entry_points=[CommandHandler('removescore', remove_score_start)],
        states={
            REMOVE_SCORE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_score_date)],
            REMOVE_SCORE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_score_confirm)],
        },
        fallbacks=[CommandHandler('cancel', remove_score_cancel)],
        per_chat=True
    )
    
    edit_score_handler = ConversationHandler(
        entry_points=[CommandHandler('editscore', edit_score_start)],
        states={
            EDIT_SCORE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_score_date)],
            EDIT_SCORE_NEW_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_score_new_points)],
            EDIT_SCORE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_score_confirm)],
        },
        fallbacks=[CommandHandler('cancel', edit_score_cancel)],
        per_chat=True
    )
    
    start_challenge_handler = ConversationHandler(
        entry_points=[CommandHandler('startchallenge', start_challenge_command)],
        states={
            START_CHALLENGE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_challenge_desc)],
            START_CHALLENGE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_challenge_type)],
            START_CHALLENGE_SCORING: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_challenge_scoring)],
            START_CHALLENGE_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_challenge_period)],
            START_CHALLENGE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_challenge_confirm)],
        },
        fallbacks=[CommandHandler('cancel', start_challenge_cancel)],
        per_chat=True
    )
    
    add_admin_handler = ConversationHandler(
        entry_points=[CommandHandler('addadmin', add_admin_start)],
        states={
            ADD_ADMIN_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_username)],
            ADD_ADMIN_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_confirm)],
        },
        fallbacks=[CommandHandler('cancel', add_admin_cancel)],
        per_chat=True
    )
    
    remove_admin_handler = ConversationHandler(
        entry_points=[CommandHandler('removeadmin', remove_admin_start)],
        states={
            REMOVE_ADMIN_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin_username)],
            REMOVE_ADMIN_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin_confirm)],
        },
        fallbacks=[CommandHandler('cancel', remove_admin_cancel)],
        per_chat=True
    )
    
    remove_entry_handler = ConversationHandler(
        entry_points=[CommandHandler('removeentry', remove_entry_start)],
        states={
            REMOVE_ENTRY_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_entry_username)],
            REMOVE_ENTRY_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_entry_confirm)],
        },
        fallbacks=[CommandHandler('cancel', remove_entry_cancel)],
        per_chat=True
    )
    
    new_challenge_handler = ConversationHandler(
        entry_points=[CommandHandler('newsuggest', new_challenge_start)],
        states={
            NEW_CHALLENGE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_challenge_desc)],
            NEW_CHALLENGE_SCORING: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_challenge_scoring)],
            NEW_CHALLENGE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_challenge_confirm)],
        },
        fallbacks=[CommandHandler('cancel', new_challenge_cancel)],
        per_chat=True
    )
    
    setbaseline_handler = ConversationHandler(
        entry_points=[CommandHandler('setbaseline', setbaseline_start)],
        states={
            BASELINE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setbaseline_value)],
        },
        fallbacks=[CommandHandler('cancel', setbaseline_cancel)],
        per_chat=True
    )
    
    updatevalue_handler = ConversationHandler(
        entry_points=[CommandHandler('updatevalue', updatevalue_start)],
        states={
            UPDATE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, updatevalue_value)],
        },
        fallbacks=[CommandHandler('cancel', updatevalue_cancel)],
        per_chat=True
    )
    
    edit_challenge_handler = ConversationHandler(
        entry_points=[CommandHandler('editchallenge', edit_challenge_start)],
        states={
            EDIT_CHALLENGE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_challenge_select)],
            EDIT_CHALLENGE_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_challenge_field)],
            EDIT_CHALLENGE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_challenge_value)],
            EDIT_CHALLENGE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_challenge_confirm)],
        },
        fallbacks=[CommandHandler('cancel', edit_challenge_cancel)],
        per_chat=True
    )
    
    remove_challenge_handler = ConversationHandler(
        entry_points=[CommandHandler('removechallenge', remove_challenge_start)],
        states={
            REMOVE_CHALLENGE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_challenge_select)],
            REMOVE_CHALLENGE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_challenge_confirm)],
        },
        fallbacks=[CommandHandler('cancel', remove_challenge_cancel)],
        per_chat=True
    )
    
    show_feedback_handler = ConversationHandler(
        entry_points=[CommandHandler('showfeedback', show_feedback_start)],
        states={
            FEEDBACK_VIEWING: [MessageHandler(filters.TEXT & ~filters.COMMAND, show_feedback_next)],
        },
        fallbacks=[CommandHandler('cancel', show_feedback_cancel)],
        per_chat=True
    )
    
    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_member))
    
    # Add conversation handlers
    application.add_handler(register_handler)
    application.add_handler(add_score_handler)
    application.add_handler(remove_score_handler)
    application.add_handler(edit_score_handler)
    application.add_handler(start_challenge_handler)
    application.add_handler(add_admin_handler)
    application.add_handler(remove_admin_handler)
    application.add_handler(remove_entry_handler)
    application.add_handler(new_challenge_handler)
    application.add_handler(setbaseline_handler)
    application.add_handler(updatevalue_handler)
    application.add_handler(edit_challenge_handler)
    application.add_handler(remove_challenge_handler)
    application.add_handler(show_feedback_handler)
    
    # Add command handlers
    application.add_handler(CommandHandler('stats', stats))
    application.add_handler(CommandHandler('statsweek', stats_week))
    application.add_handler(CommandHandler('statslastweek', stats_last_week))
    application.add_handler(CommandHandler('challenge', challenge))
    application.add_handler(CommandHandler('nextchallenge', next_challenge))
    application.add_handler(CommandHandler('pastchallenges', past_challenges))
    application.add_handler(CommandHandler('admins', admins))
    application.add_handler(CommandHandler('cancel', cancel_command))
    application.add_handler(CommandHandler('feedback', feedback_command))
    
    # Add change challenge leaderboard commands
    application.add_handler(CommandHandler('statsgain', stats_gain))
    application.add_handler(CommandHandler('statsloss', stats_loss))
    application.add_handler(CommandHandler('statschange', stats_change))
    
    # Add message handlers for voting (must be after conversation handlers)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
        handle_vote_or_suggestion
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
        handle_past_challenge_selection
    ))
    
    # Schedule notification checking at specific Finnish times
    job_queue = application.job_queue
    
    # Run at midnight Finnish time (00:00) for final results and status updates
    job_queue.run_daily(
        check_challenge_notifications, 
        time=time(hour=22, minute=0),  # 22:00 UTC = 00:00 Finnish time (UTC+2)
        name="midnight_finnish_check"
    )
    
    # Run at noon Finnish time (12:00) for challenge start notifications
    job_queue.run_daily(
        check_challenge_notifications,
        time=time(hour=10, minute=0),  # 10:00 UTC = 12:00 Finnish time (UTC+2)
        name="noon_finnish_check"
    )
    
    # Run at 6 PM Finnish time (18:00) for challenge end notifications
    job_queue.run_daily(
        check_challenge_notifications,
        time=time(hour=16, minute=0),  # 16:00 UTC = 18:00 Finnish time (UTC+2)
        name="evening_finnish_check"
    )
    
    # Run the bot
    print("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
