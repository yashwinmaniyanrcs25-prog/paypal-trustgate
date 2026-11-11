import { test, expect } from '@playwright/test';

test.describe('Purchase Proposals & Mandate Staging', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Purchase Proposals/i }).first().click();
  });

  test('renders AI mandate composer header and sub-tabs', async ({ page }) => {
    await expect(page.locator('text=AI Intent Mandate Composer & Policy Engine')).toBeVisible();
    await expect(page.locator('button', { hasText: /Natural Language Composer/i })).toBeVisible();
    await expect(page.locator('button', { hasText: /Policy Rule Matrix/i })).toBeVisible();
  });

  test('displays prompt presets and input textarea', async ({ page }) => {
    const textarea = page.locator('textarea');
    await expect(textarea).toBeVisible();

    // Check sample presets
    await expect(page.locator('text=Mechanical Keyboard under $140')).toBeVisible();

    // Click sample preset
    await page.locator('text=Mechanical Keyboard under $140').click();
    await expect(textarea).toHaveValue(/keyboard/i);
  });

  test('switches to Policy Rule Matrix and verifies TG-001 through TG-007', async ({ page }) => {
    await page.locator('button', { hasText: /Policy Rule Matrix/i }).click();

    await expect(page.locator('text=TG-001')).toBeVisible();
    await expect(page.locator('text=TG-002')).toBeVisible();
    await expect(page.locator('text=TG-003')).toBeVisible();
    await expect(page.locator('text=TG-004')).toBeVisible();
    await expect(page.locator('text=TG-005')).toBeVisible();
    await expect(page.locator('text=TG-006')).toBeVisible();
    await expect(page.locator('text=TG-007')).toBeVisible();
  });
});

