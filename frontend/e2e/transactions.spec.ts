import { test, expect } from '@playwright/test';

test.describe('Transactions Ledger & Forensic View', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Transactions/i }).first().click();
  });

  test('renders transactions ledger table and filters', async ({ page }) => {
    await expect(page.locator('text=Persisted Transaction Ledger')).toBeVisible();

    // Verify search input
    const searchInput = page.locator('input[placeholder*="Search by ID"]');
    await expect(searchInput).toBeVisible();

    // Verify status filter button or dropdown
    await expect(page.locator('button', { hasText: /Status/i }).or(page.locator('text=All Statuses'))).toBeVisible();
  });

  test('displays column headers for transaction attributes', async ({ page }) => {
    await expect(page.locator('th', { hasText: /Transaction ID/i })).toBeVisible();
    await expect(page.locator('th', { hasText: /Product/i })).toBeVisible();
    await expect(page.locator('th', { hasText: /Amount/i })).toBeVisible();
    await expect(page.locator('th', { hasText: /Status/i })).toBeVisible();
  });
});

