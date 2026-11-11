import { test, expect } from '@playwright/test';

test.describe('Product Discovery & Policy Evaluation Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Discover Products/i }).first().click();
  });

  test('renders discovery header and marketplace mode switches', async ({ page }) => {
    await expect(page.locator('text=Multi-Marketplace Discovery & Compliance Pre-Check')).toBeVisible();
    await expect(page.locator('button', { hasText: 'Channel3' })).toBeVisible();
    await expect(page.locator('button', { hasText: 'Demo Catalog' })).toBeVisible();
  });

  test('renders active purchase mandate constraints banner', async ({ page }) => {
    await expect(page.locator('text=Active Mandate Constraints')).toBeVisible();
    await expect(page.locator('text=Max Budget:')).toBeVisible();
  });

  test('switches to Demo Catalog mode and executes discovery search', async ({ page }) => {
    // Select Demo Catalog mode
    await page.locator('button', { hasText: 'Demo Catalog' }).click();

    // Query input
    const searchInput = page.locator('input[placeholder*="keyboard"], input[type="text"]').first();
    await expect(searchInput).toBeVisible();

    // Click search button
    const searchBtn = page.getByRole('button', { name: /search/i }).first();
    await searchBtn.click();

    // Wait for search response cards to appear
    await expect(page.locator('text=Deterministic Policy Evaluations').or(page.locator('text=Candidates Found'))).toBeVisible({ timeout: 10000 });
  });
});

