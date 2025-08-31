# Telegram Competition Bot - Chat Flow Examples

This document provides detailed examples of conversation flows, expected inputs, and bot responses for the competition tracking Telegram bot.

## Basic Commands (No Conversation Flow)

### `/start`
**Trigger:** First interaction with bot or when user types `/start`
**Context:** Any chat type
**Response:**
```
🎯 Welcome to the Monthly Competition Bot! 🎯

Available commands:
📋 /help - Show detailed help
👤 /register - Register for competitions (private only)
📊 /stats - Current month leaderboard
📈 /statsweek - This week's leaderboard
📉 /statslastweek - Last week's leaderboard
➕ /addscore - Add your scores (private only)
🎯 /challenge - View current challenge
🔮 /nextchallenge - Upcoming challenges

Admin commands (if you're an admin):
🚀 /startchallenge - Create new challenge (private only)
👑 /addadmin - Add new admin (private only)

Use /help for detailed explanations!
```

### `/help`
**Trigger:** User types `/help`
**Context:** Any chat type
**Response:** Detailed help message with all available commands and explanations.

### `/stats`, `/statsweek`, `/statslastweek`, `/statsgain`, `/statsloss`, `/statschange`
**Trigger:** User types any stats command
**Context:** Any chat type
**Response:** Formatted leaderboard showing rankings, usernames, and scores for the specified period.

---

## Conversation Flows

### 1. User Registration (`/register`)

**Entry Point:** `/register` command
**Restriction:** Private messages only
**States:** `REGISTER_USERNAME`

#### Flow Example:
```
👤 User: /register

🤖 Bot: Please enter the username you'd like to register for competitions:

👤 User: JohnDoe

🤖 Bot: ✅ Registration successful! You're registered as 'JohnDoe' for competitions.
```

#### Error Cases:
- **Group Chat Usage:**
  ```
  👤 User: /register
  🤖 Bot: Please use this command in a private message.
  ```

- **Username Too Short:**
  ```
  👤 User: Jo
  🤖 Bot: Username must be at least 3 characters. Please try again:
  ```

- **Username Too Long:**
  ```
  👤 User: ThisIsAVeryLongUsernameThatExceedsLimit
  🤖 Bot: Username must be 20 characters or less. Please try again:
  ```

#### Cancellation:
```
👤 User: /cancel
🤖 Bot: Registration cancelled.
```

---

### 2. Add Score (`/addscore`)

**Entry Point:** `/addscore` command
**Restriction:** Private messages only
**States:** `ADD_SCORE_DATE` → `ADD_SCORE_POINTS` → `ADD_SCORE_CONFIRM`

#### Flow Example:
```
👤 User: /addscore

🤖 Bot: Enter the date(s) for scoring:
- Single day: 15
- Date range: 6-10
- Cancel with /cancel

👤 User: 15

🤖 Bot: Enter your points for day 15:

👤 User: 25

🤖 Bot: 📊 **Confirm Score Addition** 📊

**Challenge:** Daily Steps Challenge
**Date(s):** 15th
**Points:** 25

Type 'yes' to confirm, anything else to cancel:

👤 User: yes

🤖 Bot: ✅ Score added successfully! Points: 25 for day 15.
```

#### Date Range Example:
```
👤 User: /addscore

🤖 Bot: Enter the date(s) for scoring:
- Single day: 15
- Date range: 6-10
- Cancel with /cancel

👤 User: 6-10

🤖 Bot: Enter your points for days 6-10:

👤 User: 120

🤖 Bot: 📊 **Confirm Score Addition** 📊

**Challenge:** Daily Steps Challenge
**Date(s):** 6th-10th
**Points:** 120

Type 'yes' to confirm, anything else to cancel:

👤 User: yes

🤖 Bot: ✅ Score added successfully! Points: 120 for days 6-10.
```

#### Error Cases:
- **No Active Challenge:**
  ```
  👤 User: /addscore
  🤖 Bot: No active challenge found.
  ```

- **Invalid Date Format:**
  ```
  👤 User: abc
  🤖 Bot: Invalid date format. Please use single day (15) or range (6-10):
  ```

- **Challenge Not Active:**
  ```
  👤 User: /addscore
  🤖 Bot: Cannot add scores right now. Challenge status: Ended - Grace period expired
  ```

---

### 3. Remove Score (`/removescore`)

**Entry Point:** `/removescore` command
**Restriction:** Private messages only
**States:** `REMOVE_SCORE_DATE` → `REMOVE_SCORE_CONFIRM`

#### Flow Example:
```
👤 User: /removescore

🤖 Bot: Enter the date(s) to remove points from:
- Single day: 15
- Date range: 6-10
- Cancel with /cancel

👤 User: 15

🤖 Bot: 📊 **Confirm Score Removal** 📊

**Challenge:** Daily Steps Challenge
**Date(s):** 15th
**Points to Remove:** 25 (1 entries)

Type 'yes' to confirm, anything else to cancel:

👤 User: yes

🤖 Bot: ✅ Score removed successfully! Removed 1 entries for day 15.
```

---

### 4. Edit Score (`/editscore`)

**Entry Point:** `/editscore` command
**Restriction:** Private messages only
**States:** `EDIT_SCORE_DATE` → `EDIT_SCORE_NEW_POINTS` → `EDIT_SCORE_CONFIRM`

#### Flow Example:
```
👤 User: /editscore

🤖 Bot: Enter the date(s) to edit points for:
- Single day: 15
- Date range: 6-10
- Cancel with /cancel

👤 User: 15

🤖 Bot: 📊 **Current Points for day 15:** 25

Enter new points for day 15:

👤 User: 30

🤖 Bot: 📊 **Confirm Score Edit** 📊

**Challenge:** Daily Steps Challenge
**Date(s):** 15th
**Old Points:** 25
**New Points:** 30

Type 'yes' to confirm, anything else to cancel:

👤 User: yes

🤖 Bot: ✅ Score edited successfully! Updated points to 30 for day 15.
```

---

### 5. Start Challenge - Admin Only (`/startchallenge`)

**Entry Point:** `/startchallenge` command
**Restriction:** Private messages only, Admin users only
**States:** `START_CHALLENGE_DESC` → `START_CHALLENGE_TYPE` → `START_CHALLENGE_SCORING` → `START_CHALLENGE_PERIOD` → `START_CHALLENGE_CONFIRM`

#### Flow Example:
```
👤 Admin: /startchallenge

🤖 Bot: Enter the challenge description:

👤 Admin: Daily Steps Challenge - Track your daily steps for the month

🤖 Bot: What type of challenge is this?

1️⃣ **Standard** - Regular point tracking
2️⃣ **Change** - Track improvements/changes from baseline

Reply with '1' for standard or '2' for change:

👤 Admin: 1

🤖 Bot: Enter scoring description (what are points measuring):

👤 Admin: Steps in thousands (1 point = 1000 steps)

🤖 Bot: Enter challenge period:

1️⃣ **This Month** - Start immediately, end at month end
2️⃣ **Next Month** - Start next month, end at that month end
3️⃣ **Custom Range** - Specify exact dates

Reply with '1', '2', or '3':

👤 Admin: 1

🤖 Bot: 📊 **Confirm Challenge Creation** 📊

**Description:** Daily Steps Challenge - Track your daily steps for the month
**Type:** Standard
**Scoring:** Steps in thousands (1 point = 1000 steps)
**Period:** This Month (Dec 1-31, 2024)

Type 'yes' to confirm, anything else to cancel:

👤 Admin: yes

🤖 Bot: ✅ Challenge created successfully!

📢 Challenge will be announced to the group shortly.
```

#### Error Cases:
- **Non-Admin User:**
  ```
  👤 User: /startchallenge
  🤖 Bot: This command is for admins only.
  ```

- **Description Too Short:**
  ```
  👤 Admin: Short desc
  🤖 Bot: Description should be at least 10 characters. Please try again:
  ```

---

### 6. Add Admin (`/addadmin`)

**Entry Point:** `/addadmin` command
**Restriction:** Private messages only, Admin users only
**States:** `ADD_ADMIN_USERNAME` → `ADD_ADMIN_CONFIRM`

#### Flow Example:
```
👤 Admin: /addadmin

🤖 Bot: Enter the Telegram username (without @) to make admin:

👤 Admin: johndoe

🤖 Bot: 📊 **Confirm Add Admin** 📊

**Username:** @johndoe

Type 'yes' to confirm, anything else to cancel:

👤 Admin: yes

🤖 Bot: ✅ Successfully added @johndoe as admin.
```

#### Error Cases:
- **User Not Found:**
  ```
  👤 Admin: johndoe
  🤖 Bot: User @johndoe not found. They need to interact with the bot first.
  ```

- **User Already Admin:**
  ```
  👤 Admin: johndoe
  🤖 Bot: @johndoe is already an admin.
  ```

---

### 7. New Challenge Suggestion (`/newsuggest`)

**Entry Point:** `/newsuggest` command
**Restriction:** Any chat type
**States:** `NEW_CHALLENGE_DESC` → `NEW_CHALLENGE_SCORING` → `NEW_CHALLENGE_CONFIRM`

#### Flow Example:
```
👤 User: /newsuggest

🤖 Bot: Enter challenge description (verify it's unique before suggesting):

👤 User: Daily Reading Challenge - Track pages read per day

🤖 Bot: Enter scoring description (what the points measure):

👤 User: Pages read (1 point = 1 page)

🤖 Bot: 📊 **Confirm Challenge Suggestion** 📊

**Description:** Daily Reading Challenge - Track pages read per day
**Scoring:** Pages read (1 point = 1 page)

Type 'yes' to submit suggestion, anything else to cancel:

👤 User: yes

🤖 Bot: Challenge suggestion submitted!
```

#### Error Cases:
- **Too Many Suggestions:**
  ```
  👤 User: yes
  🤖 Bot: You can only have a maximum of 3 suggestions.
  ```

---

### 8. Set Baseline - Change Challenges (`/setbaseline`)

**Entry Point:** `/setbaseline` command
**Restriction:** Private messages only, Change challenges only
**States:** `BASELINE_VALUE`

#### Flow Example:
```
👤 User: /setbaseline

🤖 Bot: 📊 **Setting Baseline Value** 📊

**Challenge:** Weight Loss Challenge
**Measuring:** Weight in kg

Enter your starting value (numbers only, e.g., '75.5', '8500'):

👤 User: 85.5

🤖 Bot: ✅ Baseline set successfully!

**Your baseline:** 85.5

You can now track changes using /updatevalue
```

#### Error Cases:
- **Not a Change Challenge:**
  ```
  👤 User: /setbaseline
  🤖 Bot: This command is only for change-based challenges.
  ```

- **Invalid Number:**
  ```
  👤 User: abc
  🤖 Bot: Please enter a valid number (e.g., '75.5', '8500'):
  ```

---

### 9. Update Value - Change Challenges (`/updatevalue`)

**Entry Point:** `/updatevalue` command
**Restriction:** Private messages only, Change challenges only
**States:** `UPDATE_VALUE`

#### Flow Example:
```
👤 User: /updatevalue

🤖 Bot: 📊 **Update Your Value** 📊

**Baseline:** 85.5
**Current:** 85.5

Enter your new value:

👤 User: 83.2

🤖 Bot: ✅ Value updated successfully!

**Baseline:** 85.5
**Current:** 83.2
**Change:** -2.3 ⬇️

Points will be calculated based on your progress!
```

#### Error Cases:
- **No Baseline Set:**
  ```
  👤 User: /updatevalue
  🤖 Bot: You haven't set a baseline value yet. Use /setbaseline to set your starting value.
  ```

---

## Group Chat Interactions

### Challenge Voting
When challenges are posted in group chats, users can vote using numbers:

```
🤖 Bot: 🗳️ **Choose Next Challenge** 🗳️

Vote by replying with the number:

1️⃣ Daily Steps Challenge - Track daily steps
2️⃣ Reading Pages Challenge - Track pages read daily  
3️⃣ Water Intake Challenge - Track glasses of water

Current votes: 📊
1️⃣ Daily Steps: 5 votes
2️⃣ Reading Pages: 3 votes
3️⃣ Water Intake: 2 votes

👤 User: 1

🤖 Bot: ✅ Vote recorded! Thanks for voting on the Daily Steps Challenge.

Current votes: 📊
1️⃣ Daily Steps: 6 votes
2️⃣ Reading Pages: 3 votes
3️⃣ Water Intake: 2 votes
```

### New Member Welcome
When someone joins the group:

```
🤖 Bot: 👋 Welcome @newuser to our Monthly Competition Group!

To participate in competitions:
1. Send me a private message
2. Use /register to sign up
3. Check /challenge for current competition

Good luck and have fun! 🎯
```

---

## Error Handling

### Common Error Responses:

1. **Command in wrong chat type:**
   ```
   Please use this command in a private message.
   ```

2. **Non-admin trying admin commands:**
   ```
   This command is for admins only.
   ```

3. **No active challenge:**
   ```
   No active challenge found.
   ```

4. **Invalid input format:**
   ```
   Invalid format. Please try again:
   ```

5. **Challenge status prevents action:**
   ```
   Cannot add scores right now. Challenge status: [status message]
   ```

### Cancellation
All conversation flows support cancellation with `/cancel`:
```
👤 User: /cancel
🤖 Bot: [Operation] cancelled.
```

---

## Notes

- All private message operations include validation for chat type
- Admin operations include user permission checks
- Score operations validate against active challenge status
- Date inputs support both single days (15) and ranges (6-10)
- Confirmation steps are required for all data-modifying operations
- The bot maintains conversation state per user for multi-step interactions