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
        
        // Call this after some delay so the server has enough time to set up IDLE()
        setTimeout(fetch_watch_message, 1 * 1000); // 1 second
    });

    $( "select[name='folder']" ).change(function() {
        // Open a new socket watching the another folder
        request_watch_message();
        // console.log( $(this).find("option:selected").text() );
    });

    // Apply rule on the current message
    $( "#rule-container" ).on("click", "button", function(e) {
        // If no message
        // then alert("No message is selected! Please mark the message read/unread to select the message!");
        if(!btn_watch.is(":hidden")) {
            alert('No message is selected! Click "Watch" button in order to select a message');
            return;
        }
        
        if(latest_watched_message) { // TODO fix this
            alert("No message is selected! Please mark the message read/unread to select a message!");
            return;
        }

        $(this).attr("er-id");

        kargs = {};
        $(this).parents("tr").find("li").each(function(index, elem) {
            kargs[$(elem).attr("name")] = $(elem).find('input').val();
        })

        console.log(kargs)

        // TODO remove this hardcode 
        // fetch_components('datepicker');

        // var iframe = document.createElement('iframe');
        // var html = '<body>Foo</body>';
        // iframe.src = 'data:text/html;charset=utf-8,' + encodeURI(html);
        // document.body.appendChild(iframe);
        // console.log('iframe.contentWindow =', iframe.contentWindow);
    })

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

    function fetch_components(component) {
        var params = {
            "component": component
        };
        
        $.post('/load_components', params,
            function(res) {
                console.log(res);

                if (res.status) {
                    $("#option-container").append( res['template'] );
                }
                else {
                    notify(res, false);
                }
            }
        ).fail(function(res) {
            alert("Please refresh the page!");
        });
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

                    // TODO if the message is from a different folder, noop 

                    if( latest_watched_message != res['uid'] ) {
                        watching_msg_container.text( res['message']['subject'] + " (" + res['message']['date'] + ")"  );
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
                // This function doesn't return
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
