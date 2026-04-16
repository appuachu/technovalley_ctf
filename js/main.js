// Enhanced Main JavaScript for TechnovallyCTF

$(document).ready(function() {
    // Auto-hide alerts after 5 seconds with fade
    $('.alert').each(function() {
        const alert = $(this);
        setTimeout(function() {
            alert.fadeOut('slow', function() {
                alert.remove();
            });
        }, 5000);
    });

    // Add smooth scrolling for anchor links
    $('a[href^="#"]').on('click', function(e) {
        e.preventDefault();
        const target = $(this).attr('href');
        if (target !== '#') {
            $('html, body').animate({
                scrollTop: $(target).offset().top - 70
            }, 500);
        }
    });

    // Add scroll reveal animation
    const revealElements = $('.scroll-reveal');
    if (revealElements.length) {
        const revealOnScroll = function() {
            revealElements.each(function() {
                const elementTop = $(this).offset().top;
                const windowBottom = $(window).scrollTop() + $(window).height();
                if (elementTop < windowBottom - 100) {
                    $(this).addClass('revealed');
                }
            });
        };
        $(window).on('scroll', revealOnScroll);
        revealOnScroll();
    }

    // Add tooltip initialization if Bootstrap tooltips are used
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Global functions
function confirmAction(message) {
    return confirm(message || 'Are you sure you want to perform this action?');
}

function showAlert(type, message, duration = 5000) {
    const icon = type === 'success' ? 'check-circle-fill' :
                 type === 'danger' ? 'exclamation-octagon-fill' :
                 type === 'warning' ? 'exclamation-triangle-fill' : 'info-circle-fill';

    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show shadow-lg" role="alert" style="border-radius: 16px; border-left: 4px solid ${type === 'success' ? '#10b981' : type === 'danger' ? '#ef4444' : '#f59e0b'};">
            <i class="bi bi-${icon} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    $('.container.mt-4').prepend(alertHtml);

    setTimeout(function() {
        $('.alert').fadeOut('slow', function() {
            $(this).remove();
        });
    }, duration);
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        showAlert('success', '✓ Copied to clipboard!', 2000);
    }).catch(function() {
        showAlert('danger', 'Failed to copy text', 2000);
    });
}

function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Add loading state to buttons
function setButtonLoading(button, isLoading, originalText = null) {
    if (isLoading) {
        button.data('original-text', button.html());
        button.prop('disabled', true);
        button.html('<span class="spinner-border spinner-border-sm me-2"></span> Loading...');
    } else {
        button.prop('disabled', false);
        button.html(button.data('original-text') || originalText || 'Submit');
    }
}
