import { test, expect } from '@playwright/test';

test.describe('Dashboard View & Telemetry', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('renders security perimeter hero card and title', async ({ page }) => {
    await expect(page.locator('text=PayPal TrustGate Agentic Commerce Guard')).toBeVisible();
    await expect(page.locator('text=Dual-Layer Security Perimeter & SQLite ACID Ledger Active')).toBeVisible();
    await expect(page.locator('text=zero payment authorization rights')).toBeVisible();
  });

  test('displays 4 core status metric cards', async ({ page }) => {
    // 1. AI Payment Privilege (ZERO AUTH)
    await expect(page.locator('text=AI Payment Privilege')).toBeVisible();
    await expect(page.locator('text=ZERO AUTH')).toBeVisible();

    // 2. Intent Interpreter
    await expect(page.locator('text=Groq Intent Interpreter')).toBeVisible();

    // 3. Policy Engine & Ledger
    await expect(page.locator('text=Policy Engine & Ledger')).toBeVisible();

    // 4. PayPal Gateway
    await expect(page.locator('text=PayPal Gateway')).toBeVisible();
  });

  test('renders executive trust telemetry section', async ({ page }) => {
    await expect(page.locator('text=Executive Trust & Policy Telemetry')).toBeVisible();
    await expect(page.locator('text=Live data from /api/v1/audit/summary')).toBeVisible();
  });

  test('renders quick navigation action cards', async ({ page }) => {
    await expect(page.locator('text=Search Catalog')).toBeVisible();
    await expect(page.locator('text=Compose Mandate')).toBeVisible();
    await expect(page.locator('text=Approval Center')).toBeVisible();
  });
});

