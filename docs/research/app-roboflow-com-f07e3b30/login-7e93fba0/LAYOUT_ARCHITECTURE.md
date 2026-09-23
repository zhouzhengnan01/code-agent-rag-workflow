# Layout Architecture

The page is a fixed full-viewport grid. Desktop uses equal-width columns. The left side independently centers a constrained workflow while brand and footer remain pinned by `justify-content: space-between`. The right side is a clipped, layered animation surface. At 820px the grid collapses to one column and the promo is removed from layout.
