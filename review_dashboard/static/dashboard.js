document.addEventListener("DOMContentLoaded", () => {
  for (const form of document.querySelectorAll("[data-confirm-review]")) {
    form.querySelectorAll('button[type="submit"]').forEach((button) => {
      button.addEventListener("click", (event) => {
        if (button.disabled) return;
        const action = button.value;
        if (action === "reject" && !window.confirm("Reject this mystery and close its private review PR? This will NOT publish it.")) {
          event.preventDefault();
        }
        if (action === "advance" && !window.confirm("Advance this candidate to HUMAN PLAYTESTING only? Its private review PR will close; nothing is published.")) {
          event.preventDefault();
        }
      });
    });
  }
});