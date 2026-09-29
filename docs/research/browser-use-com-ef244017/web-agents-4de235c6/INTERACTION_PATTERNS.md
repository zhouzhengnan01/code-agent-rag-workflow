# Interaction patterns

- Primary links and buttons: color/background transitions 150ms; pill CTAs compress to 96% scale on active. Keyboard focus uses a 2px pumpkin ring and 2px offset.
- Hero artwork: hover `scale(1.035)` over 1 second; reduced-motion disables scaling/transition.
- Header: fixed backdrop at 85% black; menu controls reveal grouped links; keyboard Escape closes the compact menu.
- Feature figures: reveal/animate once when entering the viewport. The source matrix and progress bars start at opacity/width zero and are triggered by scroll visibility.
- Code examples: tab control changes selected snippet and copy-button accessible name; copy reports a temporary confirmation, without a network request.
- FAQ and mobile footer: disclosure buttons update `aria-expanded`; answer region opens/closes; chevron rotates 180° over 300ms.
- Cookie notice: local-only choice, persistent via localStorage; Accept/Reject closes it. No third-party analytics are included.
