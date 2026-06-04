import { test, expect, Page } from '@playwright/test';

const APP_URL = 'https://vpn.assurehub.io';
const TIMEOUT_MS = 30000;

test.describe('VPN Health Monitor Dashboard', () => {
  let page: Page;

  test.beforeEach(async ({ browser }) => {
    const context = await browser.newContext({
      ignoreHTTPSErrors: true // For self-signed certs in dev
    });
    page = await context.newPage();
    await page.goto(APP_URL, { waitUntil: 'networkidle' });
  });

  test('should load dashboard and display header', async () => {
    // Check page title
    await expect(page).toHaveTitle(/VPN Health Monitor/i);

    // Check header elements
    const header = page.locator('header');
    await expect(header).toBeVisible();

    const title = page.locator('h1');
    await expect(title).toContainText('VPN Health Monitor Dashboard');

    // Check status badge exists
    const statusBadge = page.locator('.status-badge');
    await expect(statusBadge).toBeVisible();
  });

  test('should display cluster information', async () => {
    // Wait for cluster info to load
    const clusterInfo = page.locator('#clusterInfo');
    await expect(clusterInfo).toBeVisible({ timeout: TIMEOUT_MS });

    // Check pod information is displayed
    const podName = page.locator('.info-value').first();
    await expect(podName).not.toBeEmpty();

    // Check all info items are visible
    const infoItems = page.locator('.info-item');
    await expect(infoItems).toHaveCount(5); // Pod Name, Namespace, IP, VPC, Cluster CIDRS
  });

  test('should display provider cards and stats', async () => {
    // Wait for dashboard to load
    const dashboard = page.locator('#dashboard');
    await expect(dashboard).toBeVisible({ timeout: TIMEOUT_MS });

    // Check stat cards are displayed
    const statCards = page.locator('.stat-card');
    await expect(statCards).toHaveCount(4); // Total, Healthy, Unhealthy, Errors

    // Check stat values are populated
    const statValues = page.locator('.stat-value');
    for (const value of await statValues.all()) {
      const text = await value.textContent();
      await expect(text).not.toBe('-');
    }

    // Check provider cards exist
    const providerCards = page.locator('.provider-card');
    await expect(providerCards.count()).toBeGreaterThan(0);
  });

  test('should collapse provider cards by default', async () => {
    await page.waitForSelector('.provider-card', { timeout: TIMEOUT_MS });

    // Get first provider card
    const firstCard = page.locator('.provider-card').first();
    const targetsGrid = firstCard.locator('.targets-grid');

    // Check that targets grid is collapsed by default
    const isCollapsed = await targetsGrid.evaluate(el =>
      el.classList.contains('collapsed')
    );
    expect(isCollapsed).toBe(true);
  });

  test('should expand/collapse provider card on header click', async () => {
    await page.waitForSelector('.provider-card', { timeout: TIMEOUT_MS });

    const firstCard = page.locator('.provider-card').first();
    const header = firstCard.locator('.provider-header');
    const targetsGrid = firstCard.locator('.targets-grid');
    const toggleIcon = firstCard.locator('.toggle-icon');

    // Initially collapsed
    let isCollapsed = await targetsGrid.evaluate(el =>
      el.classList.contains('collapsed')
    );
    expect(isCollapsed).toBe(true);

    // Click to expand
    await header.click();
    await page.waitForTimeout(300); // Wait for animation

    isCollapsed = await targetsGrid.evaluate(el =>
      el.classList.contains('collapsed')
    );
    expect(isCollapsed).toBe(false);

    // Icon should rotate
    const isIconCollapsed = await toggleIcon.evaluate(el =>
      el.classList.contains('collapsed')
    );
    expect(isIconCollapsed).toBe(false);

    // Click to collapse
    await header.click();
    await page.waitForTimeout(300);

    isCollapsed = await targetsGrid.evaluate(el =>
      el.classList.contains('collapsed')
    );
    expect(isCollapsed).toBe(true);
  });

  test('should collapse/expand all cards with header buttons', async () => {
    await page.waitForSelector('.provider-card', { timeout: TIMEOUT_MS });

    const collapseBtn = page.locator('button:has-text("Collapse All")');
    const expandBtn = page.locator('button:has-text("Expand All")');

    await expect(collapseBtn).toBeVisible();
    await expect(expandBtn).toBeVisible();

    // Click expand all
    await expandBtn.click();
    await page.waitForTimeout(300);

    const targetsGrids = page.locator('.targets-grid');
    const gridCount = await targetsGrids.count();

    // Check all are expanded
    for (let i = 0; i < gridCount; i++) {
      const isCollapsed = await targetsGrids.nth(i).evaluate(el =>
        el.classList.contains('collapsed')
      );
      expect(isCollapsed).toBe(false);
    }

    // Click collapse all
    await collapseBtn.click();
    await page.waitForTimeout(300);

    // Check all are collapsed
    for (let i = 0; i < gridCount; i++) {
      const isCollapsed = await targetsGrids.nth(i).evaluate(el =>
        el.classList.contains('collapsed')
      );
      expect(isCollapsed).toBe(true);
    }
  });

  test('should display tunnel status indicators', async () => {
    await page.waitForSelector('.provider-card', { timeout: TIMEOUT_MS });

    // Check tunnel indicators exist
    const tunnelIndicators = page.locator('.tunnel-indicator');
    if (await tunnelIndicators.count() > 0) {
      const indicator = tunnelIndicators.first();
      await expect(indicator).toBeVisible();

      // Check for status text
      const statusText = await indicator.textContent();
      expect(statusText).toMatch(/Tunnel: (UP|DOWN|UNKNOWN)/i);
    }
  });

  test('should open diagnostics modal', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await expect(diagnosticsBtn).toBeVisible();

    // Click diagnostics button
    await diagnosticsBtn.click();

    // Wait for modal to appear
    const modal = page.locator('.modal-overlay.active');
    await expect(modal).toBeVisible();

    // Check modal title
    const modalTitle = page.locator('h2:has-text("Network Diagnostics")');
    await expect(modalTitle).toBeVisible();
  });

  test('should display all diagnostic commands in dropdown', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    await expect(commandSelect).toBeVisible();

    const options = page.locator('#diagnosticCommand option');
    const optionCount = await options.count();

    // Should have: placeholder + PING + DIG + TELNET + SSH + CURL + TRACEROUTE
    expect(optionCount).toBeGreaterThanOrEqual(7);

    // Check specific commands exist
    await expect(page.locator('#diagnosticCommand')).toHaveValue('');
    await commandSelect.selectOption('ping');
    await expect(commandSelect).toHaveValue('ping');
  });

  test('should validate PING form fields', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const targetInput = page.locator('#diagnosticTarget');
    const countField = page.locator('#diagnosticCount');

    // Select PING
    await commandSelect.selectOption('ping');

    // Count field should be visible
    await expect(countField).toBeVisible();

    // Check default count value
    const countValue = await countField.inputValue();
    expect(countValue).toBe('4');

    // Enter target
    await targetInput.fill('8.8.8.8');
    await expect(targetInput).toHaveValue('8.8.8.8');
  });

  test('should validate DIG form fields', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const recordTypeSelect = page.locator('#recordType');
    const dnsServerInput = page.locator('#dnsServer');

    // Select DIG
    await commandSelect.selectOption('dig');

    // Record type field should be visible
    await expect(recordTypeSelect).toBeVisible();

    // Check record type options
    const recordTypeOptions = page.locator('#recordType option');
    const optionCount = await recordTypeOptions.count();
    expect(optionCount).toBeGreaterThanOrEqual(7); // A, AAAA, MX, NS, TXT, CNAME, SOA

    // DNS server field should be visible
    await expect(dnsServerInput).toBeVisible();

    // Enter DNS server
    await dnsServerInput.fill('8.8.8.8');
    await expect(dnsServerInput).toHaveValue('8.8.8.8');
  });

  test('should validate CURL form fields', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const methodSelect = page.locator('#curlMethod');
    const protocolSelect = page.locator('#curlProtocol');
    const headersTextarea = page.locator('#curlHeaders');
    const bodyTextarea = page.locator('#curlBody');
    const followRedirectsCheckbox = page.locator('#curlFollowRedirects');
    const insecureCheckbox = page.locator('#curlInsecure');
    const portInput = page.locator('#diagnosticPort');

    // Select CURL
    await commandSelect.selectOption('curl');

    // All fields should be visible
    await expect(methodSelect).toBeVisible();
    await expect(protocolSelect).toBeVisible();
    await expect(headersTextarea).toBeVisible();
    await expect(bodyTextarea).toBeVisible();
    await expect(followRedirectsCheckbox).toBeVisible();
    await expect(insecureCheckbox).toBeVisible();
    await expect(portInput).toBeVisible();

    // Check default values
    await expect(methodSelect).toHaveValue('GET');
    await expect(protocolSelect).toHaveValue('https');

    // Set custom values
    await methodSelect.selectOption('POST');
    await expect(methodSelect).toHaveValue('POST');

    await headersTextarea.fill('Content-Type: application/json\nAuthorization: Bearer token');
    await expect(headersTextarea).toContainText('Content-Type');

    await bodyTextarea.fill('{"key":"value"}');
    await expect(bodyTextarea).toHaveValue('{"key":"value"}');

    await followRedirectsCheckbox.check();
    await expect(followRedirectsCheckbox).toBeChecked();

    await insecureCheckbox.check();
    await expect(insecureCheckbox).toBeChecked();
  });

  test('should validate SSH form fields', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const usernameInput = page.locator('#sshUsername');
    const verboseCheckbox = page.locator('#sshVerbose');
    const portInput = page.locator('#diagnosticPort');

    // Select SSH
    await commandSelect.selectOption('ssh');

    // Fields should be visible
    await expect(usernameInput).toBeVisible();
    await expect(verboseCheckbox).toBeVisible();
    await expect(portInput).toBeVisible();

    // Check default values
    const usernameValue = await usernameInput.inputValue();
    expect(usernameValue).toBe('root');

    const portValue = await portInput.inputValue();
    expect(portValue).toBe('22');

    // Set custom username
    await usernameInput.fill('admin');
    await expect(usernameInput).toHaveValue('admin');

    // Check verbose option
    await verboseCheckbox.check();
    await expect(verboseCheckbox).toBeChecked();
  });

  test('should validate TRACEROUTE form fields', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const maxHopsInput = page.locator('#maxHops');
    const timeoutInput = page.locator('#hopTimeout');

    // Select TRACEROUTE
    await commandSelect.selectOption('traceroute');

    // Fields should be visible
    await expect(maxHopsInput).toBeVisible();
    await expect(timeoutInput).toBeVisible();

    // Check default values
    await expect(maxHopsInput).toHaveValue('30');
    await expect(timeoutInput).toHaveValue('5');

    // Set custom values
    await maxHopsInput.fill('15');
    await expect(maxHopsInput).toHaveValue('15');

    await timeoutInput.fill('10');
    await expect(timeoutInput).toHaveValue('10');
  });

  test('should validate IP:PORT common ports dropdown', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const commonPortsSelect = page.locator('#commonPorts');
    const portInput = page.locator('#diagnosticPort');
    const targetInput = page.locator('#diagnosticTarget');

    // Select TELNET (port-based command)
    await commandSelect.selectOption('telnet');

    // Common ports dropdown should be visible
    await expect(commonPortsSelect).toBeVisible();

    // Enter target
    await targetInput.fill('192.168.1.1');

    // Select HTTP from common ports
    await commonPortsSelect.selectOption('80');

    // Port input should be updated
    await expect(portInput).toHaveValue('80');

    // Select HTTPS from common ports
    await commonPortsSelect.selectOption('443');
    await expect(portInput).toHaveValue('443');
  });

  test('should update target preview in real-time', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const targetInput = page.locator('#diagnosticTarget');
    const portInput = page.locator('#diagnosticPort');
    const targetPreview = page.locator('#targetPreview');

    // Select CURL (port-based)
    await commandSelect.selectOption('curl');

    // Enter target
    await targetInput.fill('api.example.com');
    await page.waitForTimeout(100);

    // Check preview updates
    let preview = await targetPreview.textContent();
    expect(preview).toContain('api.example.com');

    // Change port
    await portInput.fill('8443');
    await page.waitForTimeout(100);

    preview = await targetPreview.textContent();
    expect(preview).toBe('api.example.com:8443');
  });

  test('should require target before execution', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const executeBtn = page.locator('#executeDiagnosticsBtn');

    // Execute button should be disabled initially
    await expect(executeBtn).toBeDisabled();

    // Select command
    await commandSelect.selectOption('ping');

    // Button should still be disabled without target
    await expect(executeBtn).toBeDisabled();

    // Enter target
    const targetInput = page.locator('#diagnosticTarget');
    await targetInput.fill('8.8.8.8');

    // Button should now be enabled
    await expect(executeBtn).toBeEnabled();
  });

  test('should close diagnostics modal', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const modal = page.locator('.modal-overlay.active');
    await expect(modal).toBeVisible();

    // Close button should exist
    const closeBtn = page.locator('button:has-text("✕")');
    await closeBtn.click();

    // Modal should be hidden
    await expect(modal).not.toHaveClass(/active/);
  });

  test('should execute PING command and show output', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const targetInput = page.locator('#diagnosticTarget');
    const executeBtn = page.locator('#executeDiagnosticsBtn');
    const terminal = page.locator('#terminalOutput');

    // Select PING
    await commandSelect.selectOption('ping');

    // Enter target (localhost for speed)
    await targetInput.fill('127.0.0.1');

    // Execute
    await executeBtn.click();

    // Wait for output
    await expect(terminal).toContainText('ping', { timeout: TIMEOUT_MS });

    // Should show command prompt
    const lines = await terminal.locator('.terminal-line').count();
    expect(lines).toBeGreaterThan(0);

    // Wait for completion
    await page.waitForSelector('.terminal-line:has-text("[Exit Code")', {
      timeout: TIMEOUT_MS
    });
  });

  test('should display command execution timing', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const targetInput = page.locator('#diagnosticTarget');
    const executeBtn = page.locator('#executeDiagnosticsBtn');
    const terminal = page.locator('#terminalOutput');

    // Select PING
    await commandSelect.selectOption('ping');
    await targetInput.fill('127.0.0.1');
    await executeBtn.click();

    // Wait for duration display
    await page.waitForSelector('.terminal-line:has-text("[Duration")', {
      timeout: TIMEOUT_MS
    });

    // Check duration format
    const terminalText = await terminal.textContent();
    expect(terminalText).toMatch(/\[Duration: \d+\.\d+s\]/);
  });

  test('should display exit code', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const targetInput = page.locator('#diagnosticTarget');
    const executeBtn = page.locator('#executeDiagnosticsBtn');
    const terminal = page.locator('#terminalOutput');

    // Select PING
    await commandSelect.selectOption('ping');
    await targetInput.fill('127.0.0.1');
    await executeBtn.click();

    // Wait for exit code display
    await page.waitForSelector('.terminal-line:has-text("[Exit Code")', {
      timeout: TIMEOUT_MS
    });

    const terminalText = await terminal.textContent();
    expect(terminalText).toMatch(/\[Exit Code: \d+\]/);
  });

  test('should handle invalid IP addresses', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const targetInput = page.locator('#diagnosticTarget');
    const executeBtn = page.locator('#executeDiagnosticsBtn');
    const terminal = page.locator('#terminalOutput');

    // Select PING
    await commandSelect.selectOption('ping');

    // Enter invalid IP
    await targetInput.fill('invalid-ip-address');
    await executeBtn.click();

    // Should show error
    await expect(terminal).toContainText(/Invalid|Error/, { timeout: 5000 });
  });

  test('should display success metrics on healthy targets', async () => {
    await page.waitForSelector('.provider-card', { timeout: TIMEOUT_MS });

    // Expand a provider card
    const firstCard = page.locator('.provider-card').first();
    const header = firstCard.locator('.provider-header');
    await header.click();
    await page.waitForTimeout(300);

    // Look for target elements with metrics
    const targets = firstCard.locator('.target');
    if (await targets.count() > 0) {
      const firstTarget = targets.first();

      // Check for metrics
      const targetName = firstTarget.locator('.target-name');
      await expect(targetName).toBeVisible();

      const metrics = firstTarget.locator('.metric');
      expect(await metrics.count()).toBeGreaterThan(0);

      // Check for specific metric labels
      await expect(firstTarget).toContainText(/Status|Latency|Success Rate|Last Ping/);
    }
  });

  test('should update dashboard data periodically', async () => {
    // Get initial stats
    const healthyCountInitial = await page.locator('#healthyCount').textContent();

    // Wait for refresh cycle (10 seconds)
    await page.waitForTimeout(12000);

    // Check if data is still visible (should be refreshed)
    const healthyCountFinal = await page.locator('#healthyCount').textContent();

    // Should still have content
    expect(healthyCountFinal).not.toBe('-');
  });

  test('should handle network errors gracefully', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    const commandSelect = page.locator('#diagnosticCommand');
    const targetInput = page.locator('#diagnosticTarget');
    const executeBtn = page.locator('#executeDiagnosticsBtn');

    // Select PING
    await commandSelect.selectOption('ping');

    // Enter unreachable address
    await targetInput.fill('192.0.2.1'); // TEST-NET-1 reserved range

    await executeBtn.click();

    // Should complete without crashing
    const terminal = page.locator('#terminalOutput');
    await expect(terminal).toBeVisible({ timeout: TIMEOUT_MS });

    // Check for completion
    const lines = await terminal.locator('.terminal-line').count();
    expect(lines).toBeGreaterThan(0);
  });

  test('should clear terminal on button click', async () => {
    const diagnosticsBtn = page.locator('button:has-text("🔧")');
    await diagnosticsBtn.click();

    // Execute a command first
    const commandSelect = page.locator('#diagnosticCommand');
    const targetInput = page.locator('#diagnosticTarget');
    const executeBtn = page.locator('#executeDiagnosticsBtn');
    const clearBtn = page.locator('button:has-text("Clear")');

    await commandSelect.selectOption('ping');
    await targetInput.fill('127.0.0.1');
    await executeBtn.click();

    // Wait for output
    const terminal = page.locator('#terminalOutput');
    await expect(terminal).toContainText('ping', { timeout: TIMEOUT_MS });

    // Clear terminal
    await clearBtn.click();

    // Check terminal is cleared
    const terminalText = await terminal.textContent();
    expect(terminalText).toContain('Terminal cleared');
  });
});
