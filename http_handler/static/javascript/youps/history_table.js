var _message_data, _contact_data; // This global variable to pass around the row data
var log_backup = {}, user_status_backup = "";

$(document).ready(function() {
    $("#btn-log-load-more").click(function() {
        fetch_log(false);
        $(this).hide();
    });
})


function append_log( msg_log, is_error ) {
    if(!msg_log) return;  
        var sorted = [];
        for(var key in msg_log) {
            sorted[sorted.length] = key;
        }
        sorted.sort();
        // sorted.reverse(); // 

        var t = $('#console-table').DataTable();
        $.each(sorted, function(index, timestamp) {     
            try {
                Message = msg_log[timestamp];
                if (Message && !"timestamp" in Message) return;
                _message_data = Message;
                // alert(Message["trigger"]);
    
                var json_panel_id = timestamp.replace(/[ /:,]/g,'');
                t.row.add( [
                        timestamp.split(",")[0],
                        '<span class="label label-info">{0}</span>'.format(Message["trigger"] || ""),
                        '<div class="jsonpanel contact" id="jsonpanel-from-{0}"></div>'.format(json_panel_id),
                        '<div class="jsonpanel" id="jsonpanel-{0}"></div>'.format(json_panel_id),
                        (Message["error"] ? '<span class="label label-danger">Error</span>' : "") + Message['log']
                ] ).draw( false );  
    
                // Delete attributes that are not allowed for users 
                delete Message["trigger"];
                delete Message["error"];
                delete Message["log"];
                delete Message["timestamp"];
                delete Message["type"];
    
                Contact :  Message['from_']
                $('#jsonpanel-from-' + json_panel_id).jsonpanel({
                    data: {
                        Contact :  Message['from_']
                    }
                });
    
                // set contact object preview 
                $('#jsonpanel-from-' + json_panel_id + " .val-inner").text(
                    '"{0}", '.format(Message['from_']['name']) + '"{0}", '.format(Message['from_']['email'])  + '"{0}", '.format(Message['from_']['organization'])  + '"{0}", '.format(Message['from_']['geolocation'])  );
    
                
                $('#jsonpanel-' + json_panel_id).jsonpanel({
                    data: {
                        Message : Message
                    }
                });
    
                // set msg object preview 
                var preview_msg = '{0}: "{1}", '.format("subject", Message['subject']) +  '{0}: "{1}", '.format("folder", Message['folder']);
                for (var key in Message) {
                    if (Message.hasOwnProperty(key)) {
                        preview_msg += '{0}: "{1}", '.format(key, Message[key])
                    }
                }
                $("#jsonpanel-" + json_panel_id + " .val-inner").text( preview_msg );
            
            }
              catch(err) {
                console.log(err);
            }
            
        });

        // recent msg at top
        $("#console-table").DataTable().order([0, 'des']).draw();   

    // var datetime = format_date();
    // $( "<p>{0}</p>".format(datetime)).prependTo( "#console-output" ).addClass("info");
}   

function fetch_log(recent_only=true) {
    var params = {
        "recent_only": recent_only
    };
    
    $.post('/fetch_execution_log', params,
        function(res) {
            // $('#donotsend-msg').hide();
            // console.log(res);
            
            // Auth success
            if (res.status) {
                // Update execution log
                if( Object.keys(log_backup).length != Object.keys(JSON.parse(res['imap_log'])).length){
                    msg_log = JSON.parse(res['imap_log']);

                    // if it's a first time loading the log, display only recent 10 messages then enalbe 'load more' btn.
                    if(Object.keys(log_backup).length == 0) {
                        var recent_keys = Object.keys(msg_log).sort(function(a, b) {return a>b;}).slice(-10);
                        append_log( recent_keys.reduce(function(o, k) { o[k] = msg_log[k]; return o; }, {}) );
                        
                    }

                    else {
                        old_log = log_backup;

                        // append new logs from the server
                        var new_msg_key = $(Object.keys(msg_log)).not(Object.keys(old_log)).get();
                        
                        append_log(new_msg_key.reduce((a, c) => ({ ...a, [c]: msg_log[c] }), {}), false);
                    }
                        //replace(/: True/g, ': true').replace(/: False/g, ': false').replace(/\'/g, '"').replace(/\</g, '&lt;').replace(/\>/g, '&gt;'));
                    // msg_log = JSON.parse(res['imap_log'].replace(/: True/g, ': true').replace(/: False/g, ': false').replace(/\'/g, '"').replace(/\</g, '&lt;').replace(/\>/g, '&gt;'));
                    

                    
                }
                log_backup = JSON.parse(res['imap_log']);
            }
            else {
                notify(res, false);

                if('imap_authenticated' in res && !res['imap_authenticated']) {
                    alert(res["code"]);
                    window.location.href = "/editor"
                }

            }

            setTimeout(fetch_log, 2 * 1000); // 2 second
        }
    ).fail(function(res) {
        alert("Please refresh the page!");
    });
}

$(document).ready(function() {
    var table = $('#console-table').DataTable( {
        "bPaginate": false,
        "bLengthChange": false,
        "bFilter": true,
        "bInfo": false,
        "bAutoWidth": false,
        "columnDefs": [
            { "type": "html-input", "targets": [2, 3] }
        ],
        "columns": [
            { "width": "40px" },
            { "orderable": false },
            { "width": "200px", "orderable": false },
            { "width": "400px", "orderable": false },
            { "orderable": false }
        ],
        "order": [[1, 'asc']],
        "drawCallback": function( settings ) {
            
        }
    } );

    $.fn.dataTableExt.ofnSearch['html-input'] = function(el) {
        // Fire after a row is drew
        return JSON.stringify(_message_data);
    };
    
    // Add event listener for opening and closing details
    $('.console-table tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = table.row( tr );

        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            // Open this row
            row.child( format(row.data()) ).show();
            tr.addClass('shown');
        }
    } );
})
