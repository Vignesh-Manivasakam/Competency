/**
 * Playwright E2E test: Full user journey.
 *
 * From spec §15.1 (E2E layer):
 * Manager creates competency → Employee completes session → Mastery updated.
 *
 * Prerequisites: Backend running at http://localhost:8000, Frontend at http://localhost:5173.
 * Run with: npx playwright test
 */
import { test, expect } from '@playwright/test';

test.describe('Full User Journey', () => {
  const BASE_URL = 'http://localhost:5173';

  test('Manager creates competency and employee completes session', async ({ page }) => {
    // Step 1: Manager logs in
    await page.goto(`${BASE_URL}/login`);
    await page.fill('[data-testid="email-input"]', 'manager@example.com');
    await page.fill('[data-testid="password-input"]', 'SecureP@ssw0rd!');
    await page.click('[data-testid="login-button"]');

    // Wait for dashboard to load
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({
      timeout: 10000,
    });

    // Step 2: Navigate to competencies and create one
    await page.click('[data-testid="nav-competencies"]');
    await page.click('[data-testid="create-competency-btn"]');

    await page.fill('[data-testid="competency-name"]', 'Backend Engineering');
    await page.fill(
      '[data-testid="competency-description"]',
      'Full-stack backend development skills including API design and databases'
    );
    await page.click('[data-testid="submit-competency"]');

    // Verify competency created
    await expect(page.locator('text=Backend Engineering')).toBeVisible({
      timeout: 5000,
    });

    // Step 3: Trigger decomposition
    await page.click('[data-testid="decompose-btn"]');

    // Wait for AI decomposition (may take a few seconds)
    await expect(page.locator('[data-testid="skill-tree"]')).toBeVisible({
      timeout: 30000,
    });

    // Step 4: Manager logs out, employee logs in
    await page.click('[data-testid="user-menu"]');
    await page.click('[data-testid="logout-btn"]');

    await page.fill('[data-testid="email-input"]', 'employee@example.com');
    await page.fill('[data-testid="password-input"]', 'SecureP@ssw0rd!');
    await page.click('[data-testid="login-button"]');

    // Step 5: Employee starts a learning session
    await page.click('[data-testid="nav-learning"]');
    await page.click('[data-testid="start-session-btn"]');

    // Wait for content to load
    await expect(page.locator('[data-testid="session-content"]')).toBeVisible({
      timeout: 15000,
    });

    // Step 6: Employee interacts with the tutor
    await page.fill(
      '[data-testid="learner-input"]',
      'I think decorators wrap functions to add behavior.'
    );
    await page.click('[data-testid="submit-response"]');

    // Wait for AI scoring and next content
    await expect(page.locator('[data-testid="feedback-section"]')).toBeVisible({
      timeout: 15000,
    });

    // Step 7: Verify mastery progress is tracked
    await page.click('[data-testid="nav-progress"]');
    await expect(page.locator('[data-testid="mastery-indicator"]')).toBeVisible({
      timeout: 5000,
    });
  });

  test('Health check endpoint is accessible', async ({ page }) => {
    const response = await page.request.get('http://localhost:8000/health');
    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body.status).toBe('ok');
  });
});
