import { test, expect } from '@playwright/test';

test.describe('Navigation Section Switching', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('navigates through all 7 primary views', async ({ page }) => {
    // 1. Dashboard
    await expect(page.locator('text=PayPal TrustGate Agentic Commerce Guard')).toBeVisible();

    // 2. Discover Products
    await page.getByRole('button', { name: /Discover Products/i }).first().click();
    await expect(page.locator('text=Multi-Marketplace Discovery & Compliance Pre-Check')).toBeVisible();

    // 3. Purchase Proposals
    await page.getByRole('button', { name: /Purchase Proposals/i }).first().click();
    await expect(page.locator('text=AI Intent Mandate Composer & Policy Engine')).toBeVisible();

    // 4. Approval Center
    await page.getByRole('button', { name: /Approval Center/i }).first().click();
    await expect(page.locator('text=Human Approval & Checkout Gate')).toBeVisible();

    // 5. Transactions
    await page.getByRole('button', { name: /Transactions/i }).first().click();
    await expect(page.locator('text=Persisted Transaction Ledger')).toBeVisible();

    // 6. Audit Trail
    await page.getByRole('button', { name: /Audit Trail/i }).first().click();
    await expect(page.locator('text=Cryptographic SHA-256 Audit Trail')).toBeVisible();

    // 7. Settings
    await page.getByRole('button', { name: /Settings/i }).first().click();
    await expect(page.locator('text=Environment & API Gateway Diagnostics')).toBeVisible();
  });
});

