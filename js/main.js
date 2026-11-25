(function () {
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var header = document.querySelector(".site-header");
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  var heroImg = document.querySelector(".hero-media img");

  function onScroll() {
    if (header) header.classList.toggle("is-shrunk", window.scrollY > 20);
    if (heroImg && !reduced) {
      var y = Math.min(window.scrollY, 700);
      heroImg.style.transform = "translate3d(0," + y * 0.22 + "px,0) scale(1.08)";
    }
  }
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = document.body.classList.toggle("nav-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.addEventListener("click", function (event) {
      if (event.target.closest("a")) {
        document.body.classList.remove("nav-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        document.body.classList.remove("nav-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  var revealNodes = document.querySelectorAll(".reveal");
  if (reduced || !("IntersectionObserver" in window)) {
    revealNodes.forEach(function (node) { node.classList.add("in"); });
  } else {
    var revealObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          revealObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.16 });
    revealNodes.forEach(function (node) { revealObserver.observe(node); });
  }

  document.querySelectorAll("[data-count]").forEach(function (el) {
    var target = Number(el.getAttribute("data-count"));
    var decimals = Number(el.getAttribute("data-decimals") || "0");
    var suffix = el.getAttribute("data-suffix") || "";
    function render(value) {
      el.textContent = value.toFixed(decimals) + suffix;
    }
    if (reduced || !("IntersectionObserver" in window)) {
      render(target);
      return;
    }
    var started = false;
    var counterObserver = new IntersectionObserver(function (entries) {
      if (!entries[0].isIntersecting || started) return;
      started = true;
      var start = performance.now();
      function frame(now) {
        var t = Math.min(1, (now - start) / 1100);
        var eased = 1 - Math.pow(1 - t, 3);
        render(target * eased);
        if (t < 1) requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
      counterObserver.disconnect();
    }, { threshold: 0.5 });
    counterObserver.observe(el);
  });

  document.querySelectorAll("[data-ba]").forEach(function (root) {
    var frame = root.querySelector(".ba-frame");
    var before = root.querySelector(".ba-before");
    var beforeImg = before.querySelector("img");
    var range = root.querySelector('input[type="range"]');
    var handle = root.querySelector(".ba-handle");
    function paint() {
      var width = frame.clientWidth;
      var pct = Number(range.value);
      frame.style.setProperty("--frame-w", width + "px");
      before.style.width = pct + "%";
      beforeImg.style.width = width + "px";
      handle.style.left = pct + "%";
      range.setAttribute("aria-valuetext", pct < 50 ? "Showing more of the after photo" : "Showing more of the before photo");
    }
    range.addEventListener("input", paint);
    window.addEventListener("resize", paint);
    paint();
  });

  document.querySelectorAll(".faq-item button").forEach(function (button) {
    button.addEventListener("click", function () {
      var panel = document.getElementById(button.getAttribute("aria-controls"));
      var open = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", open ? "false" : "true");
      if (panel) panel.hidden = open;
    });
  });

  var carousel = document.querySelector("[data-carousel]");
  if (carousel) {
    var track = carousel.querySelector(".carousel-track");
    var cards = Array.prototype.slice.call(track.children);
    var prev = carousel.querySelector("[data-prev]");
    var next = carousel.querySelector("[data-next]");
    var dots = carousel.querySelector(".dots");
    var index = 0;
    var timer = 0;

    function perView() {
      return window.matchMedia("(min-width: 760px)").matches ? 2 : 1;
    }
    function maxIndex() {
      return Math.max(0, cards.length - perView());
    }
    function stepSize() {
      if (cards.length < 2) return cards[0].getBoundingClientRect().width;
      return cards[1].offsetLeft - cards[0].offsetLeft;
    }
    function go(nextIndex) {
      var max = maxIndex();
      index = (nextIndex + max + 1) % (max + 1);
      track.style.transform = "translateX(" + (-index * stepSize()) + "px)";
      Array.prototype.forEach.call(dots.children, function (dot, i) {
        if (i === index) dot.setAttribute("aria-current", "true");
        else dot.removeAttribute("aria-current");
      });
    }
    function buildDots() {
      dots.innerHTML = "";
      var pages = maxIndex() + 1;
      for (var i = 0; i < pages; i++) {
        var dot = document.createElement("button");
        dot.type = "button";
        dot.setAttribute("aria-label", "Show review set " + (i + 1));
        if (i === index) dot.setAttribute("aria-current", "true");
        (function (n) {
          dot.addEventListener("click", function () { go(n); restart(); });
        })(i);
        dots.appendChild(dot);
      }
    }
    function restart() {
      window.clearInterval(timer);
      if (reduced) return;
      timer = window.setInterval(function () { go(index + 1); }, 7000);
    }
    prev.addEventListener("click", function () { go(index - 1); restart(); });
    next.addEventListener("click", function () { go(index + 1); restart(); });
    carousel.addEventListener("mouseenter", function () { window.clearInterval(timer); });
    carousel.addEventListener("mouseleave", restart);
    carousel.addEventListener("focusin", function () { window.clearInterval(timer); });
    carousel.addEventListener("focusout", restart);
    window.addEventListener("resize", function () {
      if (index > maxIndex()) index = maxIndex();
      buildDots();
      go(index);
    });
    buildDots();
    go(0);
    restart();
  }

  var shots = Array.prototype.slice.call(document.querySelectorAll(".shot"));
  var dialog = document.getElementById("lightbox");
  var lightImg = document.getElementById("lightbox-img");
  var lightCap = document.getElementById("lightbox-cap");
  var lightIndex = 0;
  function showShot(i) {
    if (!shots.length) return;
    lightIndex = (i + shots.length) % shots.length;
    var img = shots[lightIndex].querySelector("img");
    lightImg.src = img.currentSrc || img.src;
    lightImg.alt = img.alt;
    lightCap.textContent = img.alt;
    if (!dialog.open) dialog.showModal();
  }
  shots.forEach(function (shot, i) {
    shot.addEventListener("click", function () { showShot(i); });
  });
  if (dialog) {
    dialog.querySelector("[data-close]").addEventListener("click", function () { dialog.close(); });
    dialog.querySelector("[data-light-prev]").addEventListener("click", function () { showShot(lightIndex - 1); });
    dialog.querySelector("[data-light-next]").addEventListener("click", function () { showShot(lightIndex + 1); });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) dialog.close();
    });
  }

  var form = document.getElementById("estimate-form");
  if (form) {
    var error = document.getElementById("form-error");
    function value(id) { return form.querySelector("#" + id).value.trim(); }
    function compose() {
      var name = value("name");
      var phone = value("phone");
      var service = value("service");
      var area = value("area");
      var message = value("message");
      return [
        "Hi James, this is " + name + ".",
        "I would like a free estimate for " + service + ".",
        area ? "Area: " + area + "." : "",
        "My phone is " + phone + ".",
        message
      ].filter(Boolean).join(" ");
    }
    function validate() {
      var name = value("name");
      var phone = value("phone");
      var digits = phone.replace(/\D/g, "");
      if (!name) {
        error.textContent = "Add your name so James knows who to reply to.";
        form.querySelector("#name").focus();
        return false;
      }
      if (digits.length < 7) {
        error.textContent = "Add a phone number so James can reach you.";
        form.querySelector("#phone").focus();
        return false;
      }
      error.textContent = "";
      return true;
    }
    form.querySelector("[data-sms]").addEventListener("click", function () {
      if (!validate()) return;
      var href = "sms:+19042408705?&body=" + encodeURIComponent(compose());
      window.location.href = href;
    });
    form.querySelector("[data-email]").addEventListener("click", function () {
      if (!validate()) return;
      var href = "mailto:eastfloridapressurewashing@yahoo.com?subject=" +
        encodeURIComponent("Free estimate request") + "&body=" + encodeURIComponent(compose());
      window.location.href = href;
    });
  }
})();
