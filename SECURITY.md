# Security policy

Parro-HA handles school data about children and their parents, so security and privacy problems always come first.

## Report a problem privately

Please do **not** open a public issue for a security or privacy problem. Report it privately through [GitHub private vulnerability reporting](https://github.com/Paulus1337/Parro-HA/security/advisories/new).

Tell us the version of Parro-HA, what you saw and how to make it happen again. Never include passwords, tokens, sign-in links or real data about children, parents or teachers.

## What to report

- Passwords, sign-in names, tokens or sign-in codes that show up in logs, entity attributes or diagnostics, or that are stored when they should not be.
- Personal data, such as names, messages, photos or media links, that reaches more people than the README describes.
- Anything that changes data in Parro or marks something as read. The only change Parro-HA may make is a plain-text chat reply, sent by the Home Assistant user the Parro account belongs to or by something that runs without a user, such as an automation, to a conversation allowed in the options, within the documented limits.
- A way around the reply limits, the plain-text rules or the check of which Home Assistant user may send from which Parro account.
- A way around the check of which Home Assistant user may read which Parro account in the Parro card, the pop-ups, the photos or the *Get announcements* and *Get conversations* actions.
- Announcement or conversation texts in entity states or attributes while **Show announcement details** and **Show conversation details** are both off.

Problems in Parro itself are not in scope: please report those to Parro / ParnasSys.

## Supported versions

Only the latest release receives fixes, so please update before you report.
