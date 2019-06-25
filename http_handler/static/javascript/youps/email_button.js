var trackOutboundLink = function(inCategory) {
    debugger;
    if (gtag) {
        gtag('event', inCategory)
  }
}

$(document).ready(function() {
    var btn_watch= $("#btn-watch"),
        watching_msg_container = $("#watching-msg-container"),
        latest_watched_message = null;

    // Format string
    if (!String.prototype.format) {
        String.prototype.format = function() {
          var args = arguments;
          return this.replace(/{(\d+)}/g, function(match, number) { 
            return typeof args[number] != 'undefined'
              ? args[number]
              : match
            ;
          });
        };
    }
    btn_watch.click(function (e) {
        $(this).hide();

        request_watch_message();

        setTimeout(fetch_watch_message, 1 * 1000); // 1 second
    });

    $( "select[name='folder']" ).change(function() {
        // Change a watching folder
        
        console.log( $(this).find("option:selected").text() );
    });

    function show_loader( is_show ) {
        if(is_show) $(".sk-circle").show();
        else $(".sk-circle").hide();
    }

    function get_running() {
        return is_running;
    }

    function set_running(start_running) {
        // Start running
        if(start_running) {
            spinStatusCog(true);
            $("#engine-status-msg").text("Your email engine is running.");
            is_running = true;
        }
        
        // Stop running
        else {
            spinStatusCog(false);
            $("#engine-status-msg").text("Your email engine is not running at the moment.");
            is_running = false;
        }
    }
    
    function spinStatusCog(spin) {
        if(spin) {
            if( fa_sync = document.querySelector(".fa-sync"))
                fa_sync.classList.add("fa-spin");
            if( idle_mark = document.querySelector(".idle-mark"))
                idle_mark.style.display = "none";
        }
        else {
            if( fa_sync = document.querySelector(".fa-sync"))
                fa_sync.classList.remove("fa-spin");
            if( idle_mark = document.querySelector(".idle-mark"))   
                idle_mark.style.display = "inline-block";
        }
    }

    function fetch_watch_message() {
        var params = {
            "folder": $("select[name='folder']").find("option:selected").text()
        };
        
        $.post('/fetch_watch_message', params,
            function(res) {
                console.log(res);

                if (res.status) {
                    if ( !res['watch_status'] ) {
                        btn_watch.show();
                        return;
                    }
                    if( latest_watched_message != res['uid'] ) {
                        watching_msg_container.text( res['subject'] );
                    }
                    
                    latest_watched_message = res['uid'];
                }
                else if (!res['uid']) {}
                else {
                    notify(res, false);
                }

                setTimeout(fetch_watch_message, 1 * 1000); // 1 second
            }
        ).fail(function(res) {
            alert("Please refresh the page!");
        });
    }

    function request_watch_message() {
        var params = {
            "folder": $("select[name='folder']").find("option:selected").text()
        };

        $.post('/watch_current_message', params,
            function(res) {
                console.log(res);
                
                if (res.status) {
                    
                }
                else {
                    notify(res, false);
                }
            }
        ).fail(function(res) {
            alert("Please refresh the page!");
        });
    }

    show_loader(false);

    $(".default-text").blur();

    tinyMCE.init({
        mode: "textareas",
        theme: "advanced",
        theme_advanced_buttons1: "bold,italic,underline,strikethrough,|,justifyleft,justifycenter,justifyright,justifyfull,|,blockquote",
        theme_advanced_toolbar_location: "top",
        theme_advanced_toolbar_align: "left",
        theme_advanced_statusbar_location: "bottom",
        theme_advanced_resizing: true
    });
});
