# Third-party notices and credits

Parro-HA ships only its own code. This file thanks the projects it learned from and names the work it runs on.

## Shout-out to ha-parro

[ha-parro](https://github.com/carlmegens/ha-parro) by carlmegens is the other Parro integration for Home Assistant. Its own notices credit Parro-HA: its data models for children, groups and calendar items are adapted from Parro-HA, and Parro-HA's documentation and code informed its child calendars and replies. Parro-HA gladly returns the favour: every feature below started as an idea from ha-parro. Parro-HA built each one in its own way, and says so where it works differently. The ideas for 0.4.0 come from a line-by-line comparison with ha-parro 1.1.0 (commit bae1468) on 17 November 2026 and a recheck of the same version on 20 November 2026. Thank you, carlmegens!

### Version 0.3.0

- **Card editor**: set up the Parro card without editing YAML. Parro-HA builds it on Home Assistant's own form editor, with a switch for each part of the card.
- **Reading page in the sidebar**, after ha-parro's full-page Parro view. It was removed again in 0.3.1.

### Version 0.3.1

- **Title, number of announcements and group in the card editor**: a title, 1 to 20 announcements and a group, so that a card can show only the announcements of one group.
- **Pop-ups on the unread counters**: tap a counter to read its announcements or conversations, through Home Assistant's `custom_ui_more_info` hook. Parro-HA's pop-ups only show what Home Assistant already has and ask the Parro service nothing extra; only a photo is downloaded from Parro's media host when it is first shown.

### Version 0.4.0

Privacy between users:

- **Announcement details off by default**: announcement texts stay out of entity states and attributes, with the option **Show announcement details** (off for new accounts) to bring them back.
- **Texts over Home Assistant's own connection**: the Parro card and the pop-ups get their texts over an authenticated websocket that checks the viewer on every update, and the card shows them as plain text.
- **Readers per account**: a list of Home Assistant users who may read an account's texts and photos, kept in the options so that it can change at any time without signing in again. Parro-HA keeps one list instead of two, gives administrators no automatic access and keeps conversations with the account's own user. Its **Reconfigure** step for moving an account to another user is its own.
- **Texts and photos withheld after the session ends**: the Parro card and the pop-ups stop showing them at once, and every Parro entity except the two event entities becomes unavailable, until you sign in again.
- **Lean announcement events**: without **Show announcement details** they carry only the announcement ID and time, and their restored data is cut back to those keys, so that no texts land in `core.restore_state`.
- **Chat message events without details or replies**: **Conversations in the Parro card**, on for new accounts, is enough.
- **No event data in the history** for announcement and chat message events.
- **Children as an opt-in**: child devices, class sensors and child calendars only with the **Children** option, and children's profile photos as a separate opt-in.

Photos:

- **Photos without metadata**: decoded and saved again as JPEG without metadata, with the EXIF orientation applied first, from a short list of image formats, refused above a pixel limit and scaled to at most 1600 pixels, away from the event loop.
- **One photo cache** with a limit on the number of photos and on their total size, emptied when an entry unloads or its session ends.
- **Photos under their announcement**, loaded when they scroll into view with the viewer's own sign-in, into blob URLs that are released when the photo is no longer shown.
- **Tap a photo to see it larger**: the original, scaled to at most 1600 pixels.
- **A photo view that checks the reader** on every request and again after the download, and answers with `Cache-Control: private, no-store`.
- **No photo while its image entity is unavailable.**
- **A note for a photo that cannot be shown**: the card says "Photo not available" where the photo would be, and the README says why.

Parro card and pop-ups:

- **Status notes** for loading, no access, Parro not available and an ended session, and when Parro cannot be reached, the last data with its time.
- **Accessibility**: a real heading, headings for the items, 44 px touch targets, a visible keyboard focus, send errors that screen readers announce, `aria-busy` while loading and `aria-expanded` and `aria-controls` on **Show more**.
- **Show more and Show less** for long announcements, with the whole text of up to 20000 characters, also in **Get announcements**.
- **A card for one Parro account**: a card setting that pins the card to one account, chosen from the accounts the editing user may read.
- **A group setting** that shows the newest announcements of that group, picked by Home Assistant before it sends them to the card.
- **The latest message in each conversation**: conversations show the time of their latest message, and that message of up to 2000 characters for the account's own user.
- **Clear card setting errors** that name the setting that is wrong.
- **An agenda pop-up on Next event** with the start and end of the coming calendar items.

Sign-in and session:

- **A named sign-in check**: a fixed word in the log names the check that failed when the sign-in page does not look as expected.
- **The account checked after every renewal** of the session.
- **A clean stop**: the connection is closed when Home Assistant stops, so that a renewal under way is saved.

Calendar and other data:

- **One event per calendar item and time**: rows of one item at the same time are merged into one event with all its children and groups, rows of the item at other times stay events of their own, and items that are cancelled or deleted on the item itself are left out.
- **Child devices under the account device**, and up to 200 children and groups instead of 50.
- **Calendar views of up to 2000 rows** of Parro instead of 500.
- **A Next event that moves on** as soon as an item ends, without waiting for the next update.
- **No chat message event for a deleted message.**
- **Unknown instead of 0** on the unread counters when Parro refuses them.

Actions, diagnostics and documentation:

- **Get announcements and Get conversations**: response-only actions that give automations the announcements and the list of conversations.
- **Diagnostics** with the state of the entry and the time of the last successful update.
- **The hosts Home Assistant connects to**, named in the documentation.
- **Tips in the documentation** on the token links of image entities, on disabling an entity to keep its data from the other users, on keeping the Parro app for urgent messages, on installing by hand from a release and on getting new data right away.

Releases and quality:

- **A short versioning policy** in the README: what a minor and a patch version may change.
- **The checks before every release**, named in the README.
- **Card tests that always run**, with Node.js installed for them in automatic test runs.
- **A check of the card in a real browser** that passes or fails on its own, and fails when the page scrolls sideways or something in the card reaches past it.
- **A check of the files that ship**: only the integration files, without symlinks.

This acknowledgement does not imply a joint project or endorsement. ha-parro is released under this license:

```text
MIT License

Copyright (c) 2026 Parro Home Assistant integration contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Used, not included

Parro-HA runs on these projects. They come with Home Assistant, are not part of this repository and keep their own licenses:

- [Home Assistant](https://www.home-assistant.io/) (Apache License 2.0): the platform, and the frontend whose tile, calendar and picture cards the Parro card uses.
- [Pillow](https://python-pillow.org/) (MIT-CMU License): saves Parro photos again as JPEG without metadata.
- [aiohttp](https://github.com/aio-libs/aiohttp) (Apache License 2.0): the HTTPS connections to Parro.
- [voluptuous](https://github.com/alecthomas/voluptuous) (BSD 3-Clause License): checks options and action data; on newer Home Assistant versions, such as 2026.10 and 2026.11, [probatio](https://github.com/frenck/probatio) (MIT License) does this under the name voluptuous.
- [Material Design Icons](https://pictogrammers.com/library/mdi/) by Pictogrammers: the `mdi:` icons of the entities and actions, drawn by Home Assistant.
- [HACS](https://hacs.xyz/) (MIT License) and the Home Assistant Marketplace: install and update Parro-HA.

## Trademarks

Parro, ParnasSys, Topicus and the Parro parrot are trademarks of their respective owners. The icon places the Parro parrot in a house only to show which service the integration works with. Parro-HA is not affiliated with, endorsed by or sponsored by Parro, ParnasSys or Topicus. The MIT license of Parro-HA covers its code only, not those marks, school messages or photos.
