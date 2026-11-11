# Security policy

This integration handles school data about children and their parents. Security and privacy problems are taken seriously.

## Reporting a vulnerability

Do **not** open a public issue for security or privacy problems. Report them privately through [GitHub private vulnerability reporting](https://github.com/Paulus1337/Parro-HA/security/advisories/new).

Please include the version, what you observed and how to reproduce it. Never include passwords, tokens, sign-in links or real data about children, parents or teachers.

## Scope

In scope:

- Credentials, tokens or sign-in codes that are logged, exposed in entity attributes or diagnostics, or stored when they should not be.
- Personal data (names, messages, photos, media links) exposed beyond what is documented in the README.
- Any request that changes data in Parro or marks something as read. The only allowed change is a plain-text chat reply, sent by the Home Assistant user the Parro account belongs to or by something that runs without a user, such as an automation, to a conversation allowed in the options, within the documented limits.
- Ways around the reply limits, the plain-text rules or the check of which Home Assistant user may send from which Parro account.

Out of scope: problems in Parro itself. Report those to Parro / ParnasSys.

## Supported versions

Only the latest release receives fixes.
