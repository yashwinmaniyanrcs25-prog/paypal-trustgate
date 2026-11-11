import { test, expect } from '@playwright/test';

test.describe('Audit Trail & Cryptographic Verification', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Audit Trail/i }).first().click();
  });

  test('renders cryptographic hash-chain integrity status banner', async ({ page }) => {
    await expect(page.locator('text=Cryptographic Hash-Chain Integrity Status')).toBeVisible();
    await expect(
      page.locator('text=CHAIN VERIFIED').or(page.locator('text=SHA-256'))
    ).toBeVisible();
  });

  test('displays immutable audit trail ledger', async ({ page }) => {
    await expect(
      page.locator('text=Immutable Audit Trail').or(page.locator('text=Lifecycle Event Chaining Timeline'))
    ).toBeVisible();
  });
});

