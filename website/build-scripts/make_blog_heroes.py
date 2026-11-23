"""Render the hero images for the blog posts.

Not part of the site build: run it by hand when a hero needs changing, and
commit the PNGs it writes to src/assets/images/heroes/.

    uv run python website/build-scripts/make_blog_heroes.py

Heroes are shown with object-fit: cover, at 180px tall on the blog list cards
and up to 400px on the post page, so each image is 2:1 with no axes or text
near the edges and the interesting part kept to the middle.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Circle, Ellipse, Rectangle  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "src" / "assets" / "images" / "heroes"

# The site palette (src/styles.css).
NAVY = "#0f1219"
GOLD = "#b8860b"
GOLD_LIGHT = "#e0b44a"
GRAY = "#6b7280"
WHITE = "#ffffff"

W, H, DPI = 16, 8, 100  # 1600 x 800


def canvas(projection=None):
    fig = plt.figure(figsize=(W, H), dpi=DPI, facecolor=NAVY)
    ax = fig.add_axes([0, 0, 1, 1], projection=projection, facecolor=NAVY)
    ax.set_axis_off()
    return fig, ax


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=DPI, facecolor=NAVY)
    plt.close(fig)
    print(f"wrote {OUT / name}")


def rbf(a, b, length=1.0):
    return np.exp(-0.5 * (a[:, None] - b[None, :]) ** 2 / length**2)


def sphere(rng):
    """Uniform samples inside a ball: r ~ r^2, i.e. r = U^(1/3)."""
    n = 2500
    v = rng.normal(size=(n, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    r = rng.uniform(size=n) ** (1 / 3)
    pts = v * r[:, None]

    fig, ax = canvas(projection="3d")
    ax.set_facecolor(NAVY)
    ax.view_init(elev=18, azim=35)
    # Colour by radius so the even filling-out towards the surface shows.
    ax.scatter(*pts.T, c=r, cmap=matplotlib.colors.LinearSegmentedColormap.from_list(
        "g", [GRAY, GOLD, GOLD_LIGHT]), s=22, alpha=0.9, linewidths=0, depthshade=True)
    lim = 1.05
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim, lim)
    ax.set_box_aspect((1, 1, 1), zoom=1.35)
    save(fig, "samples-from-a-sphere.png")


def accuracy_of_inference(rng):
    """Bundles of bootstrapped error ellipses, as in the paper's corner plot."""
    fig, ax = canvas()
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 8)
    ax.set_aspect("equal")
    # (centre x, correlation, aspect) for each pair of parameters.
    panels = [(3.2, 0.0, 0.75), (5.6, -0.45, 0.85), (8.0, 0.0, 1.0),
              (10.4, -0.3, 1.15), (12.8, 0.05, 1.3)]
    for cx, rho, aspect in panels:
        for _ in range(140):
            sx = 0.42 * aspect * rng.lognormal(0, 0.12)
            sy = 0.42 / aspect * rng.lognormal(0, 0.12)
            r = np.clip(rho + rng.normal(0, 0.08), -0.95, 0.95)
            cov = np.array([[sx**2, r * sx * sy], [r * sx * sy, sy**2]])
            vals, vecs = np.linalg.eigh(cov)
            angle = np.degrees(np.arctan2(vecs[1, 1], vecs[0, 1]))
            ax.add_patch(Ellipse((cx + rng.normal(0, 0.02), 4 + rng.normal(0, 0.02)),
                                 4 * np.sqrt(vals[1]), 4 * np.sqrt(vals[0]), angle=angle,
                                 fill=False, lw=0.7, ec=GOLD_LIGHT, alpha=0.1))
        ax.plot(cx, 4, "o", ms=3, color=WHITE, alpha=0.8)
    save(fig, "accuracy-of-inference.png")


def unpredictability_of_sports(rng):
    """Favourite-vs-underdog scoreline probabilities; upsets in gold."""
    from math import exp, factorial

    pois = lambda k, lam: lam**k * exp(-lam) / factorial(k)  # noqa: E731
    fig, ax = canvas()
    ax.set_xlim(-1.2, 10.2)
    ax.set_ylim(-0.95, 4.75)
    ax.set_aspect("equal")
    for fav in range(10):
        for dog in range(5):
            p = pois(fav, 1.7) * pois(dog, 1.0)
            colour = GOLD_LIGHT if dog > fav else (GRAY if dog == fav else "#9ca3af")
            ax.add_patch(Circle((fav, dog), 0.07 + 1.1 * np.sqrt(p), color=colour,
                                alpha=0.95 if dog > fav else 0.55, lw=0))
    save(fig, "unpredictability-of-sports.png")


def gp_posterior(rng):
    """A GP posterior: mean, 2-sigma band, a few draws, and the training data."""
    f = lambda x: np.sin(1.2 * x) + 0.3 * np.cos(3.1 * x)  # noqa: E731
    xt = np.array([-6.2, -4.9, -3.1, -0.6, 0.4, 2.7, 4.1, 6.4])
    yt = f(xt)
    xp = np.linspace(-9, 9, 500)
    noise = 1e-4
    K = rbf(xt, xt) + noise * np.eye(len(xt))
    Ks = rbf(xp, xt)
    Kinv = np.linalg.inv(K)
    mean = Ks @ Kinv @ yt
    cov = rbf(xp, xp) - Ks @ Kinv @ Ks.T
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))
    draws = rng.multivariate_normal(mean, cov + 1e-8 * np.eye(len(xp)), size=5,
                                    method="cholesky")

    fig, ax = canvas()
    ax.set_xlim(-8, 8)
    ax.set_ylim(-3.4, 3.4)
    ax.fill_between(xp, mean - 2 * sd, mean + 2 * sd, color=GOLD, alpha=0.18, lw=0)
    for d in draws:
        ax.plot(xp, d, color=GRAY, lw=1.1, alpha=0.7)
    ax.plot(xp, mean, color=GOLD_LIGHT, lw=3)
    ax.plot(xt, yt, "o", ms=10, color=WHITE, mec=NAVY, mew=2)
    save(fig, "gaussian-process-demo.png")


def gp_update_equations(rng):
    """The joint covariance matrix, partitioned into T, C^T, C and P."""
    xt = np.sort(rng.uniform(-3, 3, 14))  # training inputs
    xp = np.linspace(-3.5, 3.5, 10)  # prediction inputs
    x = np.concatenate([xt, xp])
    sigma = rbf(x, x, length=1.1)
    n, m = len(xt), len(x)

    fig, ax = canvas()
    # Square matrix centred in the 2:1 frame, inset so a cover crop keeps it.
    size = 7.0
    ax.set_xlim(-8, 8)
    ax.set_ylim(-4, 4)
    ax.set_aspect("equal")
    x0, y0 = -size / 2 + 1.2, -size / 2
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("nv", [NAVY, "#3a3020", GOLD_LIGHT])
    ax.imshow(sigma, cmap=cmap, extent=(x0, x0 + size, y0, y0 + size), interpolation="nearest",
              vmin=0, vmax=1)
    split = size * n / m
    ax.plot([x0 + split] * 2, [y0, y0 + size], color=WHITE, lw=2.5)
    ax.plot([x0, x0 + size], [y0 + size - split] * 2, color=WHITE, lw=2.5)
    ax.add_patch(Rectangle((x0, y0), size, size, fill=False, ec=WHITE, lw=2.5))

    label = dict(color=WHITE, ha="center", va="center", fontsize=46, family="serif",
                 path_effects=[matplotlib.patheffects.withStroke(linewidth=6, foreground=NAVY)])
    top, left = y0 + size - split / 2, x0 + split / 2
    bottom, right = y0 + (size - split) / 2, x0 + split + (size - split) / 2
    ax.text(left, top, r"$T$", **label)
    ax.text(right, top, r"$C^{T}$", **label)
    ax.text(left, bottom, r"$C$", **label)
    ax.text(right, bottom, r"$P$", **label)
    ax.text(x0 - 0.6, 0, r"$\Sigma\ =$", **{**label, "ha": "right", "fontsize": 60})
    save(fig, "gaussian-process-update-equations.png")


if __name__ == "__main__":
    import matplotlib.patheffects  # noqa: F401  (used via matplotlib.patheffects)

    for make in (sphere, accuracy_of_inference, unpredictability_of_sports,
                 gp_posterior, gp_update_equations):
        make(np.random.default_rng(27))
