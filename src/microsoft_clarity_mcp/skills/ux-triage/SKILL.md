---
name: ux-triage
description: "A structured playbook for diagnosing user frustration and behavioral bottlenecks detected by Microsoft Clarity."
---

# UX Friction Triage Playbook

A structured playbook for diagnosing user frustration and behavioral bottlenecks detected by Microsoft Clarity.

## 1. Frustration Signals Overview

### Rage Clicks
* **Definition**: Users clicking or tapping repeatedly (3+ times in rapid succession) on the same element or area.
* **Root Causes**:
  * Unresponsive buttons or submit handlers.
  * Delayed API response without loading indicators or skeleton screens.
  * Non-interactive cards or icons styled like clickable buttons.
  * Missing visual feedback (active/focus state) on tap/click.
* **Diagnostic Steps**:
  1. Run `get_frustration_breakdown(project_id, dimension="URL")` to identify high-rage URLs.
  2. Run `get_frustration_breakdown(project_id, dimension="Device")` to isolate mobile vs desktop touch issues.
  3. Inspect recordings in Clarity dashboard filtered by `Rage Clicks`.

### Dead Clicks
* **Definition**: User clicks an element expecting an action, but no event or navigation occurs.
* **Root Causes**:
  * Static images or product photos that users expect to enlarge or link to a product page.
  * Highlighted or underlined text that resembles a hyperlink.
  * Broken `<a>` anchor tags or unhandled event delegation.
  * Disabled inputs or buttons lacking disabled styling.
* **Diagnostic Steps**:
  1. Identify top URLs with dead clicks.
  2. Audit CSS styling: remove `cursor: pointer` from non-interactive text.
  3. Add clear affordances (hyperlink styling, buttons) where users clearly want navigation.

### Quick Backs
* **Definition**: User navigates to a new page and quickly returns to the previous page (within a few seconds).
* **Root Causes**:
  * Mismatched user expectations (misleading page title, anchor text, or ad copy).
  * Slow rendering or heavy interstitial modals.
  * Low content relevance or paywalls.

### Excessive Scrolling
* **Definition**: User scrolls up and down repeatedly on a page beyond normal reading behavior.
* **Root Causes**:
  * Buried call-to-actions (CTAs) or hidden checkout buttons.
  * Poor information hierarchy or lack of table of contents.
  * Ineffective search or filtering options on product/listing pages.

## 2. Technical Health: Script & JS Errors
* **Script Error Count**: Unhandled JavaScript runtime exceptions thrown on page.
* **Error Click Count**: Clicks that directly trigger or coincide with an unhandled exception.
* **Diagnostic Steps**:
  1. Run `get_js_errors(project_id)` to isolate browser and OS combinations with error spikes.
  2. Cross-reference polyfill or modern JavaScript syntax issues on older iOS or mobile WebKit versions.
