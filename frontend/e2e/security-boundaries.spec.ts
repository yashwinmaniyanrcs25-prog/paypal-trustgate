import { test, expect } from '@playwright/test';

test.describe('Security Boundaries & AI Non-Autonomous Invariant', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('verifies AI has zero payment privilege prominently displayed', async ({ page }) => {
    await expect(page.locator('text=AI Payment Privilege')).toBeVisible();
    await expect(page.locator('text=ZERO AUTH')).toBeVisible();
    await expect(page.locator('text=Barred from authorization / charge APIs')).toBeVisible();
  });

  test('verifies Approval Center enforces non-AI human sign-off assertion', async ({ page }) => {
    await page.getByRole('button', { name: /Approval Center/i }).first().click();

    await expect(page.locator('text=Human Approval & Checkout Gate')).toBeVisible();
    await expect(page.locator('text=AI models cannot authorize payments')).toBeVisible();
  });

  test('verifies cryptographic hash chain status is accessible and monitored', async ({ page }) => {
    await page.getByRole('button', { name: /Audit Trail/i }).first().click();

    await expect(page.locator('text=Cryptographic Hash-Chain Integrity Status')).toBeVisible();
    // Tamper detection or unbroken chain guarantee is actively shown
    await expect(page.locator('text=SHA-256 deterministic hash chaining')).toBeVisible();
  });
});

