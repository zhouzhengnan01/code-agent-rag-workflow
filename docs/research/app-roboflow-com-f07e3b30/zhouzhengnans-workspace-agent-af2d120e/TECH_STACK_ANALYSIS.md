# Source and adaptation

The source page is a React application using utility-style classes, Headless UI popovers, Inter typography, and white cards over a lavender-tinted workspace. Codezzn remains a FastAPI application serving static HTML/CSS/JavaScript. Reusing the existing app architecture avoids regressions in chat streaming, skills, MCP, tasks and backend configuration. Only the presentation and landing-page navigation flow are changed.

The clone-website skill's Next.js scaffold and `npm run build` requirements do not apply to this repository. Equivalent checks here are JavaScript syntax validation, Python tests, a running local endpoint, and browser visual/interaction QA.
