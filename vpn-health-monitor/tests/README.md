# VPN Health Monitor E2E Tests

Comprehensive end-to-end test suite for the VPN Health Monitor Dashboard using Playwright.

## Overview

This test suite validates the entire VPN Health Monitor application at https://vpn.assurehub.io, including:

- Dashboard loading and display
- Cluster information visibility
- Provider card functionality (collapse/expand)
- Tunnel status indicators
- Network diagnostics modal
- All diagnostic commands (PING, DIG, TELNET, SSH, CURL, TRACEROUTE)
- Form validation and input handling
- Command execution and output display
- Error handling

## Prerequisites

- Node.js >= 18.0.0
- npm or yarn
- Playwright browsers (installed automatically)

## Installation

```bash
cd vpn-health-monitor
npm install
```

## Running Tests

### Run all tests
```bash
npm test
```

### Run in UI mode (interactive)
```bash
npm run test:ui
```

### Run in headed mode (visible browser)
```bash
npm run test:headed
```

### Run with debug mode
```bash
npm run test:debug
```

### Run specific browser
```bash
npm run test:chromium    # Chrome
npm run test:firefox     # Firefox
npm run test:webkit      # Safari
```

### Run mobile tests
```bash
npm run test:mobile
```

### View test report
```bash
npm run test:report
```

## Test Structure

### Dashboard Tests
- ✅ Page loads and displays correct title
- ✅ Cluster information displays with pod details
- ✅ Provider cards render with stats
- ✅ Cards collapse by default
- ✅ Collapse/expand functionality works
- ✅ Collapse All / Expand All buttons work
- ✅ Tunnel status indicators display
- ✅ Dashboard updates periodically

### Diagnostics Modal Tests
- ✅ Modal opens on button click
- ✅ Modal closes on close button or overlay click
- ✅ All diagnostic commands available in dropdown
- ✅ Form fields update based on selected command
- ✅ Target preview updates in real-time

### Command-Specific Tests

#### PING
- ✅ Count field displays and validates
- ✅ Default count is 4
- ✅ Executes and shows output
- ✅ Displays exit code and timing

#### DIG
- ✅ Record type dropdown shows all options (A, AAAA, MX, NS, TXT, CNAME, SOA)
- ✅ DNS server input field available
- ✅ Executes and shows DNS results

#### CURL
- ✅ HTTP method dropdown (GET, POST, PUT, DELETE, PATCH, HEAD)
- ✅ Protocol selection (HTTP/HTTPS)
- ✅ Custom headers textarea
- ✅ Request body textarea
- ✅ Follow redirects checkbox
- ✅ SSL verification toggle
- ✅ Port configuration

#### SSH
- ✅ Username field with default "root"
- ✅ Port field with default 22
- ✅ Verbose flag checkbox
- ✅ Executes and shows SSH output

#### TELNET
- ✅ Port field displays
- ✅ Executes and validates connectivity

#### TRACEROUTE
- ✅ Max hops configuration (default 30)
- ✅ Timeout per hop configuration (default 5)
- ✅ Executes and shows network path

### Common Ports Tests
- ✅ Common ports dropdown (SSH, HTTP, HTTPS, MySQL, PostgreSQL, Redis, MongoDB)
- ✅ Selecting port updates input field
- ✅ Port validation (1-65535)

### Form Validation Tests
- ✅ Execute button disabled until command and target selected
- ✅ Invalid IP addresses rejected
- ✅ Target required before execution
- ✅ Port range validation

### Error Handling Tests
- ✅ Unreachable targets handled gracefully
- ✅ Invalid inputs show appropriate errors
- ✅ Network errors don't crash app
- ✅ Terminal clears correctly

### Output Display Tests
- ✅ Terminal shows command output in real-time
- ✅ Exit codes displayed: `[Exit Code: X]`
- ✅ Execution timing displayed: `[Duration: Y.ZZs]`
- ✅ Terminal can be cleared
- ✅ Output scrolls with new lines

## Configuration

### Playwright Config (playwright.config.ts)

Key settings:
- **Test directory**: `./tests`
- **Base URL**: `https://vpn.assurehub.io`
- **Timeout**: 60 seconds
- **Expect timeout**: 10 seconds
- **Retry on CI**: 2 times
- **Reporters**: HTML, JUnit XML, JSON, List

### Browsers Tested
- Desktop Chrome
- Desktop Firefox
- Desktop Safari
- Mobile Chrome (Pixel 5)
- Mobile Safari (iPhone 12)

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 18
      - run: npm ci --prefix vpn-health-monitor
      - run: npx playwright install --with-deps
      - run: npm test --prefix vpn-health-monitor
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-report
          path: vpn-health-monitor/playwright-report/
```

## Environment Variables

```bash
CI=true              # Set for CI environments (disables retry, enables headless)
DEBUG=pw:api         # Enable Playwright debug logs
```

## Test Reports

After running tests, view the HTML report:

```bash
npm run test:report
```

Reports include:
- Test results and execution times
- Screenshots of failures
- Video recordings (optional)
- Trace files for debugging

## Debugging

### Enable Trace
Tests collect traces on first retry. View with:
```bash
npx playwright show-trace test-results/trace.zip
```

### Debug Mode
```bash
npm run test:debug
```

### Headed Browser
```bash
npm run test:headed
```

## Performance Benchmarks

Expected test execution times (on modern hardware):
- Full suite: ~3-5 minutes (depends on browser concurrency)
- Single test: ~10-30 seconds
- Dashboard load: ~2-3 seconds
- Command execution: ~5-15 seconds (network dependent)

## Troubleshooting

### Tests fail with "Target page, context or browser has been closed"
- App may have crashed. Check logs: `kubectl logs -n atg -l app=vpn-health-monitor`
- Increase timeout: Set `TIMEOUT_MS` in tests

### HTTPS certificate errors
- Config sets `ignoreHTTPSErrors: true` for dev environments
- For prod, ensure valid certificates

### Commands timeout
- Network latency may be high. Check VPN connectivity
- Increase `TIMEOUT_MS` for slower environments

### Port conflicts in Docker
- Make sure port 8000 is available
- Ensure no other VPN monitor instances running

## Maintenance

### Adding New Tests
1. Add test case to `tests/e2e.spec.ts`
2. Follow existing patterns for page locators
3. Include descriptive test names
4. Add assertions for all expected behavior

### Updating Selectors
If UI changes, update selectors in:
- `#diagnosticCommand` - Command dropdown
- `.provider-card` - Provider cards
- `.modal-overlay` - Modal overlay
- `.terminal` - Terminal output

### Performance Optimization
- Use `page.goto(APP_URL, { waitUntil: 'networkidle' })`
- Batch multiple actions in single test where logical
- Use `page.waitForTimeout()` sparingly; prefer element waits

## Contact

For issues or improvements, contact the Affinity Infrastructure Team.
