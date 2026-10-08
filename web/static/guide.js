// Student Life Guide: topic cards with copy-to-clipboard sample questions + route-map lightbox.
// All content is data-driven so new topics only need one array entry.

const TOPICS = [
  {
    title: "Visa & EMGS",
    image: "/static/assets/guides/guide-visa.png",
    blurb:
      "Student pass, EMGS approval, renewal timelines and what to prepare before you fly.",
    questions: [
      "How do I renew my student pass before it expires?",
      "What documents does EMGS require for new international students?",
    ],
  },
  {
    title: "Transport & Buses",
    image: "/static/assets/guides/guide-transport.png",
    blurb:
      "UKM campus shuttle zones, KTM komuter connections and getting to KL on a student budget.",
    questions: [
      "How do I get from UKM station to the FTSM faculty?",
      "Which campus bus zone goes to the student dormitories?",
    ],
  },
  {
    title: "Food & Halal",
    image: "/static/assets/guides/guide-food.png",
    blurb:
      "Cafeterias, mamak stalls and halal options around campus — plus what they typically cost.",
    questions: [
      "Where can I find affordable halal food near UKM?",
      "What is the average cost of a meal at the UKM cafeteria?",
    ],
  },
  {
    title: "Housing",
    image: "/static/assets/guides/guide-housing.png",
    blurb:
      "On-campus colleges vs private hostels: application steps, fees and what to bring.",
    questions: [
      "How do I apply for UKM on-campus student accommodation?",
      "What should I prepare before moving into the student college?",
    ],
  },
  {
    title: "Health & Insurance",
    image: "/static/assets/guides/guide-health.png",
    blurb:
      "Campus clinic, health insurance coverage and what to do when you feel unwell at night.",
    questions: [
      "Does UKM provide health insurance for international students?",
      "Where is the campus health clinic and what are its operating hours?",
    ],
  },
  {
    title: "Classes & Academics",
    image: "/static/assets/guides/guide-academics.png",
    blurb:
      "Course registration, exam schedules, timetables and academic calendar highlights.",
    questions: [
      "When does course registration open for the new semester?",
      "Where can I check the final exam schedule for FTSM?",
    ],
  },
];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function copyQuestion(button, question) {
  try {
    await navigator.clipboard.writeText(question);
  } catch {
    // Clipboard may be blocked (e.g. plain HTTP); fall back to a hidden textarea.
    const helper = document.createElement("textarea");
    helper.value = question;
    helper.style.position = "fixed";
    helper.style.opacity = "0";
    document.body.appendChild(helper);
    helper.select();
    try {
      document.execCommand("copy");
    } finally {
      helper.remove();
    }
  }
  button.classList.add("copied");
  window.setTimeout(() => button.classList.remove("copied"), 1400);
}

function renderCards() {
  const grid = document.getElementById("guide-cards");
  TOPICS.forEach((topic) => {
    const card = el("article", "topic-card");
    const img = document.createElement("img");
    img.src = topic.image;
    img.alt = `Illustration: ${topic.title}`;
    img.loading = "lazy";
    card.appendChild(img);

    const body = el("div", "topic-body");
    body.appendChild(el("h3", null, topic.title));
    body.appendChild(el("p", null, topic.blurb));

    const chips = el("div", "topic-chips");
    topic.questions.forEach((question) => {
      const chip = el("button", "topic-chip");
      chip.type = "button";
      const label = el("span", null, question);
      const copied = el("span", "chip-copied", "Copied ✓");
      chip.append(label, copied);
      chip.title = "Click to copy, then paste into the assistant";
      chip.addEventListener("click", () => copyQuestion(chip, question));
      chips.appendChild(chip);
    });
    body.appendChild(chips);
    card.appendChild(body);
    grid.appendChild(card);
  });
}

function setupLightbox() {
  const lightbox = document.getElementById("guide-lightbox");
  const img = document.getElementById("guide-lightbox-img");
  document.querySelectorAll("img[data-zoomable]").forEach((thumb) => {
    thumb.addEventListener("click", () => {
      img.src = thumb.src;
      img.alt = thumb.alt;
      lightbox.hidden = false;
    });
  });
  lightbox.addEventListener("click", () => {
    lightbox.hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") lightbox.hidden = true;
  });
}

renderCards();
setupLightbox();
