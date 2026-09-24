# Agent project-flow components

Observed in the authenticated Roboflow Agent interface on 2026-09-23:

1. Chat composer: multiline editable field, circular purple send button, action chips. Sending creates a titled conversation.
2. Agent confirmation card: question header with icon and collapse/close controls; numbered response buttons with descriptions; optional free-text response field. The card is inline with messages.
3. Open Asset dialog: centered modal with search, close control, tabs and recent asset rows. This is the visual reference for Codezzn's project picker.
4. New Model workspace pane: chat remains visible on the left while a new asset tab and editable creation form open on the right. The creation form contains name, visibility and type selections; nothing is created merely by opening it.
5. Asset tabs: a conversation can open more than one asset. Codezzn maps this to multiple associated projects with one active project for a turn.

The observed model-training prompt first asked the user to accept public visibility and CC BY 4.0 terms. We did not select the approval option or start training.
