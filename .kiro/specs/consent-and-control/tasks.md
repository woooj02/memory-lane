# Implementation plan

- [x] 1. /notice page (web/notice.html + route) in Nepali and English; link from the family page header; test
  - _Requirements: 1.1, 1.2, 1.3, 4.1_
- [x] 2. Pause: settings helpers, `paused_at()`, routes, `status()['paused_until']`, family page controls; tests
  - _Requirements: 2.1, 2.4_
- [x] 3. Pause applies to sync, live lines, live English and real-time reminders; tests
  - _Requirements: 2.2, 2.3_
- [x] 4. Delete: `Store.delete_conversation()` with tombstone, route, family page inline confirm, excluded everywhere; tests
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
- [x] 5. README "Privacy and consent" section; check the evening screen and /notice fit their screens
  - _Requirements: 4.2, 1.2_
