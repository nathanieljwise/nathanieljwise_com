document.addEventListener("DOMContentLoaded", () => {
    console.log("nathanieljwise.com Flask app loaded");
});

const activeLink = document.querySelector('.sidebar nav ul li a.active');
if (activeLink) {
    activeLink.scrollIntoView({ block: 'start', behavior: 'instant' });
}