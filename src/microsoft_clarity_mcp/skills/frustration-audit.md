# Behavioral UX Frustration Audit

A holistic procedure for conducting periodic UX audits across web applications using Microsoft Clarity signals.

## Audit Workflow

### 1. High-Level Vital Signs
Run `get_ux_insights(project_id, num_of_days=3)`:
* Assess **Rage Click %**: healthy threshold is typically `< 1.5%` of sessions.
* Assess **Dead Click %**: healthy threshold is `< 3.0%` of sessions.
* Assess **Quick Back %**: healthy threshold is `< 5.0%` of sessions.
* Check **Script Errors**: any nonzero script error count warrants debugging.

### 2. Dimension Segmentation
Run `get_frustration_breakdown(project_id, dimension="...")`:
* `dimension="Device"`: Compare Mobile vs Desktop vs Tablet. If mobile rage clicks significantly outpace desktop, inspect viewport responsiveness, touch target sizes (minimum 44x44px), and sticky navigation bars.
* `dimension="URL"`: Rank top 10 URLs with highest concentration of dead and rage clicks. Target these pages for priority visual fixes.
* `dimension="Browser"`: Look for outliers in Safari (iOS WebKit) vs Chrome/Firefox.

### 3. JavaScript Runtime Diagnostic
Run `get_js_errors(project_id, num_of_days=3)`:
* Map top unhandled exceptions by browser and operating system.
* Prioritize errors that correlate with user rage clicks or conversion drop-offs.
