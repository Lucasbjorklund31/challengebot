# Monthly Competition Telegram Bot Specification

## Overview
A Telegram bot for managing monthly competitions in groups with user registration, point tracking, and admin controls.

## Group Commands
- `/stats` - Show current monthly leaderboard (total points)
- `/statsweek` - Show current week's cumulative points
- `/statslastweek` - Show previous week's points
- `/challenge` - Display current challenge information
- `/nextchallenge` - View/vote on suggested challenges (numbered list)
- `/pastchallenges` - View final results from past challenges

## DM Commands (User)
- `/register` - Register username for competitions
- `/addscore` - Add points for date/period (max 100k per day)
- `/removescore` - Remove points for date/period  
- `/editscore` - Edit existing points for date/period

## DM Commands (Admin Only)
- `/admins` - List current admins
- `/addadmin` - Add admin by Telegram username
- `/removeadmin` - Remove admin by Telegram username
- `/startchallenge` - Start new challenge (description, scoring, time period)
- `/removeentry` - Remove user entry from competition

## Core Features

### Point Management
- Date input formats: single day (4) or range (6-10)
- Points distributed evenly across date ranges
- Confirmation prompts (y/n) for all add/edit/remove operations
- Maximum 100,000 points per day limit (1,000,000 total)
- Input validation for all numeric fields with error messages

### Admin System
- Bot adder becomes main admin automatically
- Admins can manage challenges and remove user entries
- Admin permissions required for sensitive operations

### Challenge System
- Current challenge display with description and scoring
- Voting system for next challenges (one vote per user)
- Users can suggest new challenges (max 3 per user)
- Past challenge results archive

### Data Structure
- User registration with custom usernames (3-20 characters, alphanumeric plus ._-)
- Daily point tracking with date association
- Weekly/monthly aggregation
- Challenge metadata and voting counts
- Admin permissions tracking
- Session data validation to prevent expired state errors

## Technical Requirements
- SQLite database for data persistence
- Date-based point calculations
- Weekly boundary handling (Monday-Sunday)
- Comprehensive input validation and error handling
- Confirmation workflows for critical operations

## Error Handling & Input Validation

### Text Input Validation
- **Empty messages**: All handlers check for missing/empty text content
- **Username validation**: 3-32 chars, alphanumeric plus underscores for admin operations
- **Registration usernames**: 3-20 chars, alphanumeric plus ._- characters
- **Description lengths**: 10-500 chars for challenges, 10-300 chars for suggestions
- **Scoring descriptions**: 5-200 chars for challenges, 5-150 chars for suggestions

### Numeric Input Validation
- **Points validation**: Positive integers only, max 1,000,000 total
- **Daily limits**: Max 100,000 points per day
- **Baseline values**: Reasonable bounds check (max 1,000,000 absolute value)
- **Date validation**: Proper format checking, future date limits

### Session Management
- **Context validation**: Checks for expired/missing session data
- **State recovery**: Graceful handling of missing conversation state
- **Database connection**: Proper error handling for all database operations

### User Experience
- **Clear error messages**: Specific guidance for each validation failure
- **Retry prompts**: Users stay in conversation flow after errors
- **Fallback handling**: Cancel options available at any point
- **Admin permission checks**: Proper authorization validation

### Common Error Responses
- "Please send a text message with [expected input]"
- "[Field] cannot be empty. Please try again:"
- "[Field] must be between X-Y characters. Please try again:"
- "Please enter a valid number (integers only):"
- "Session expired. Please start over with /[command]"
- "An error occurred. Please try again or contact an admin."