import { test, expect } from '@playwright/test';

test.describe('Approval Center & Human Sign-off Gate', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Approval Center/i }).first().click();
  });

  test('renders Approval Center header and filter buttons', async ({ page }) => {
    await expect(page.locator('text=Human Approval & Checkout Gate')).toBeVisible();
    await expect(page.locator('text=AI models cannot authorize payments')).toBeVisible();

    // Verify filter buttons exist
    await expect(page.locator('button', { hasText: /Awaiting Human Sign-off/i })).toBeVisible();
    await expect(page.locator('button', { hasText: /Approved/i })).toBeVisible();
    await expect(page.locator('button', { hasText: /Rejected/i })).toBeVisible();
    await expect(page.locator('button', { hasText: /All/i })).toBeVisible();
  });

  test('filters queue by status', async ({ page }) => {
    // Click "All" filter
    await page.locator('button', { hasText: /All/i }).click();

    // Search bar should be visible
    const searchBar = page.locator('input[placeholder*="Search by ID"]');
    await expect(searchBar).toBeVisible();
  });
});

