let currentIndex = 0;
const items = document.querySelectorAll('.carousel-item');
const captions = [
    'Image 1 Description',
    'Image 2 Description',
    'Image 3 Description'
];

function updateCarousel() {
    items.forEach((item, index) => {
        item.style.transform = `translateX(-${currentIndex * 100}%)`;
    });
    document.getElementById('caption').innerText = captions[currentIndex];
}

document.querySelector('.left').addEventListener('click', () => {
    currentIndex = (currentIndex === 0) ? items.length - 1 : currentIndex - 1;
    updateCarousel();
});

document.querySelector('.right').addEventListener('click', () => {
    currentIndex = (currentIndex === items.length - 1) ? 0 : currentIndex + 1;
    updateCarousel();
});

updateCarousel();
