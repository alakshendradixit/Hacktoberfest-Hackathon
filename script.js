// Image preview for upload fields
document.addEventListener("DOMContentLoaded", function() {
    const fileInput = document.querySelector('input[type="file"][name="food_image"]');
    const container = document.querySelector('.container');

    if (fileInput && container) {
        fileInput.addEventListener('change', function(e) {
            const imagePreview = document.getElementById('live-image-preview');
            if (imagePreview) { imagePreview.remove(); }

            if (fileInput.files && fileInput.files[0]) {
                const img = document.createElement('img');
                img.id = 'live-image-preview';
                img.className = 'uploaded-img';
                img.style.marginTop = '10px';
                img.src = URL.createObjectURL(fileInput.files[0]);
                fileInput.parentNode.insertBefore(img, fileInput.nextSibling);
            }
        });
    }

    // Add confirm for all delete buttons (in case the backend form misses it)
    container.querySelectorAll('form[action*="delete"]').forEach(form => {
        form.addEventListener('submit', function(event) {
            if(!confirm('Are you sure you want to delete this chat?')) {
                event.preventDefault();
            }
        });
    });

    // Add optional spinner on submitting forms (uncomment if you want it)
    /*
    container.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function() {
            let spinner = document.createElement('div');
            spinner.className = 'loading-spinner';
            spinner.textContent = 'Processing...';
            container.appendChild(spinner);
        });
    });
    */
});
