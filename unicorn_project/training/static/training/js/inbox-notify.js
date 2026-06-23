(function () {
  if (!document.body.dataset.inboxNotifyEnabled) {
    return;
  }

  const pollUrl = document.body.dataset.inboxPollUrl;
  if (!pollUrl) {
    return;
  }

  const pollIntervalMs = parseInt(document.body.dataset.inboxPollInterval || "60000", 10) || 60000;

  let lastCount = 0;
  let firstEvent = true;
  let audioCtx = null;

  function readBadgeCount(scope) {
    const badge = document.querySelector('[data-inbox-badge="' + scope + '"]');
    if (!badge || badge.classList.contains("d-none")) {
      return 0;
    }
    const value = parseInt(badge.textContent.trim(), 10);
    return Number.isNaN(value) ? 0 : value;
  }

  lastCount = readBadgeCount("staff") + readBadgeCount("admin");

  function getAudioContext() {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) {
      return null;
    }
    if (!audioCtx) {
      audioCtx = new AudioContext();
    }
    return audioCtx;
  }

  function unlockAudio() {
    const ctx = getAudioContext();
    if (ctx && ctx.state === "suspended") {
      ctx.resume().catch(function () {
        /* ignore */
      });
    }
  }

  document.addEventListener("click", unlockAudio);
  document.addEventListener("keydown", unlockAudio);

  function playNotificationSound() {
    try {
      const ctx = getAudioContext();
      if (!ctx) {
        return;
      }
      const playBeeps = function () {
        const tones = [880, 1174];
        tones.forEach(function (freq, index) {
          setTimeout(function () {
            const oscillator = ctx.createOscillator();
            const gain = ctx.createGain();
            oscillator.type = "sine";
            oscillator.frequency.value = freq;
            gain.gain.value = 0.15;
            oscillator.connect(gain);
            gain.connect(ctx.destination);
            oscillator.start();
            setTimeout(function () {
              oscillator.stop();
            }, 180);
          }, index * 220);
        });
      };
      if (ctx.state === "suspended") {
        ctx.resume().then(playBeeps).catch(function () {
          /* browser blocked audio until interaction */
        });
      } else {
        playBeeps();
      }
    } catch (err) {
      console.warn("Inbox notification sound failed", err);
    }
  }

  function updateBadge(scope, count) {
    document.querySelectorAll('[data-inbox-badge="' + scope + '"]').forEach(function (el) {
      if (count > 0) {
        el.textContent = String(count);
        el.classList.remove("d-none");
      } else {
        el.textContent = "";
        el.classList.add("d-none");
      }
    });
  }

  function handlePayload(data) {
    const staffCount = parseInt(data.staff_unread_count || 0, 10) || 0;
    const adminCount = parseInt(data.admin_unread_count || 0, 10) || 0;
    const totalCount = parseInt(data.unread_count || 0, 10) || staffCount + adminCount;
    updateBadge("staff", staffCount);
    updateBadge("admin", adminCount);
    if (!firstEvent && totalCount > lastCount) {
      playNotificationSound();
    }
    lastCount = totalCount;
    firstEvent = false;
  }

  function pollInbox() {
    fetch(pollUrl, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("inbox poll failed");
        }
        return response.json();
      })
      .then(handlePayload)
      .catch(function (err) {
        console.warn("Inbox poll failed", err);
      });
  }

  pollInbox();
  window.setInterval(pollInbox, pollIntervalMs);
})();
