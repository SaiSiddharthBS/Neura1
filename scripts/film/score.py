"""An original score and sound design for the Neura1 film, timed to the scene starts."""
import json, sys, wave
import numpy as np

SR = 48000
info = json.load(open(sys.argv[1]))
out = sys.argv[2]
starts, total = info["starts"], info["total"]
n = int((total + 1.0) * SR)
t = np.arange(n) / SR
mix = np.zeros((n, 2))
rng = np.random.default_rng(11)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def add(sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= n:
        return
    sig = sig[: n - i]
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    mix[i:i + len(sig), 0] += sig * gain * l * 1.41
    mix[i:i + len(sig), 1] += sig * gain * r * 1.41


def env(length, a, r):
    x = np.arange(int(length * SR)) / SR
    return np.clip(x / a, 0, 1) * np.clip((length - x) / r, 0, 1)


def pad(notes, length, a=1.6, r=2.2, bright=0.15):
    x = np.arange(int(length * SR)) / SR
    s = np.zeros_like(x)
    for m in notes:
        f = hz(m)
        for det in (-0.12, 0.0, 0.15):
            ph = rng.uniform(0, 6.28)
            s += np.sin(2 * np.pi * (f + det) * x + ph) + bright * np.sin(4 * np.pi * (f + det) * x + ph)
    return s * env(length, a, r) / (len(notes) * 3)


def pluck(m, length=0.9, decay=5.0):
    x = np.arange(int(length * SR)) / SR
    f = hz(m)
    return (np.sin(2 * np.pi * f * x) + 0.35 * np.sin(4 * np.pi * f * x) + 0.12 * np.sin(6 * np.pi * f * x)) * np.exp(-x * decay) * np.clip(x / 0.004, 0, 1)


def sub(m, length):
    x = np.arange(int(length * SR)) / SR
    return np.sin(2 * np.pi * hz(m) * x) * env(length, 0.4, 1.0)


def whoosh(length=0.9, up=True):
    k = int(length * SR)
    noise = rng.standard_normal(k)
    x = np.linspace(0, 1, k)
    # sweep a one-pole low-pass across the noise
    cut = (0.02 + 0.25 * (x if up else 1 - x)) ** 1.5
    y = np.zeros(k); acc = 0.0
    for i in range(k):
        acc += cut[i] * (noise[i] - acc); y[i] = acc
    return y * np.sin(np.pi * x) ** 1.6 * 0.9


def chime():
    a = pluck(88, 1.6, 3.2) + 0.7 * pluck(95, 1.6, 3.6)
    return a * 0.5


def bloom(length=3.0):
    x = np.arange(int(length * SR)) / SR
    return (np.sin(2 * np.pi * 55 * x) * 0.9 + np.sin(2 * np.pi * 110 * x) * 0.3) * np.exp(-x * 1.4) * np.clip(x / 0.02, 0, 1)


def riser(length=2.4):
    k = int(length * SR); x = np.linspace(0, 1, k)
    noise = rng.standard_normal(k); y = np.zeros(k); acc = 0.0
    for i in range(k):
        acc += (0.01 + 0.3 * x[i] ** 2) * (noise[i] - acc); y[i] = acc
    return y * x ** 2 * 0.8


s = starts
# --- act one: the problem (tense, sparse, A minor) ---
add(pad([45, 52, 57, 60], s[3] - s[0] + 1.5, a=2.5, r=1.8, bright=0.05), s[0], 0.22)
add(sub(33, s[3] - s[0] + 1.0), s[0], 0.16)
for k in range(int((s[3] - s[1]) / 1.2)):
    add(pluck(69 if k % 4 != 3 else 72, 0.7, 6.5), s[1] + k * 1.2, 0.05, pan=0.3 if k % 2 else -0.3)
add(chime(), s[0] + 1.45, 0.22, pan=0.1)
add(riser(2.6), s[3] - 2.4, 0.14)
add(bloom(), s[3] + 0.2, 0.32)

# --- act two: the product (warm, moving: F - C - G - Am, a soft eighth-note pulse) ---
prog = [[53, 57, 60, 64], [48, 55, 60, 64], [55, 59, 62, 67], [57, 60, 64, 67]]
roots = [41, 36, 43, 45]
bar = 2.4  # 100 bpm, one chord per bar
t0, t_end = s[3] + 0.3, s[12]
k = 0
while t0 + k * bar < t_end:
    at = t0 + k * bar
    add(pad(prog[k % 4], bar + 1.6, a=0.9, r=1.6, bright=0.18), at, 0.20)
    add(sub(roots[k % 4], bar + 0.6), at, 0.18)
    arp = [prog[k % 4][j % 4] + 24 for j in (0, 2, 1, 3, 2, 1, 3, 2)]
    if at > s[4] - 0.2:  # the pulse enters with the product
        for j, m in enumerate(arp):
            add(pluck(m, 0.6, 7.0), at + j * bar / 8, 0.035, pan=(-0.35 if j % 2 else 0.35))
    k += 1
# transitions
for i in range(4, len(s) - 1):
    add(whoosh(0.8, up=i % 2 == 0), s[i] - 0.35, 0.05, pan=(-0.4 if i % 2 else 0.4))
# --- act three: proof and close (resolve to C major) ---
add(pad([48, 55, 60, 64, 67], total - s[12] + 1.0, a=1.2, r=3.0, bright=0.2), s[12], 0.22)
add(sub(36, total - s[12]), s[12], 0.16)
for i in range(4):  # ticks as the numbers count up
    for j in range(6):
        add(pluck(96, 0.12, 40), s[13] + 1.0 + i * 0.2 + j * 0.16, 0.025)
add(bloom(3.5), s[14] + 0.2, 0.22)
add(chime(), s[14] + 1.0, 0.12)

# gentle master: fade, normalise, soft limit
fade = np.clip(t / 0.8, 0, 1) * np.clip((total + 0.6 - t) / 2.5, 0, 1)
mix *= fade[:, None]
mix /= np.abs(mix).max() / 0.6
mix = np.tanh(mix * 1.2) / np.tanh(1.2)
pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
with wave.open(out, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print("score", round(total, 1), "s")
