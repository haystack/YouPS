var _message_data, _contact_data; // This global variable to pass around the row data
var log_backup = {}, user_status_backup = "";
var log_min_id = null, log_max_id = null;

$(document).ready(function() {
    $("#btn-log-load-more").click(function() {
        fetch_log(null, log_min_id - 1);
        $(this).hide();
    });
})


$('#console-table tbody').on('click', '.btn-undo', function () {
    var logschema_id = $(this).attr("logschema_id");
    var self = this;
    var params = {"logschema-id": logschema_id};

    if (confirm("Are you sure you want to cancel this action? \n" + $(this).data("property-log"))) {
        $.post('/undo', params,
            function(res) {
                // success
                if (res.status) {
                    $(self).text('Canceled');
                    $(self).prop("disabled",true);

                    notify(res, true);
                } else {
                    notify(res, false);
                }
            }
        ).fail(function(res) {
            alert("Please refresh the page!");
        });
    }
    
    
});

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
                var property_log_json= JSON.parse(Message["property_log"]);
                var property_log = "";
                $.each(property_log_json, function(k, v) {
                    if(v["type"] == "send")
                        property_log += "- {0} {1} (can not be canceled)\n".format( v["function_name"], v["args"])
                    else if (v["type"] == "set")
                        property_log += "- {0} {1} to {2} \n".format( v["type"], v["function_name"], v["args"].length > 1 ? v["args"][1] : "")
                    else if (v["type"] == "schedule") 
                        property_log += "- {0} run the callback function\n".format(  v["function_name"].replace("_", " ") )
                    else property_log += "- {0} {1}\n".format(  v["function_name"], v["args"].length >= 1 ? v["args"][0] : "")
                });

                console.log(property_log)
                console.log(Message['subject'])

                t.row.add( [
                        timestamp.split(",")[0],
                        '<span class="label label-info">{0}</span>'.format(Message["trigger"] || ""),
                        '<div class="jsonpanel contact" id="jsonpanel-from-{0}"></div>'.format(json_panel_id),
                        '<div class="jsonpanel" id="jsonpanel-{0}"></div>'.format(json_panel_id),
                        (Message["error"] ? '<span class="label label-danger">Error</span>' : "") + Message['log'],
                        '<button type="button" logschema_id={0} class="btn btn-warning btn-undo" data-property-log="{1}">Undo</button>'.format(Message["logschema_id"], property_log)
                ] ).draw( false );  
    
                // Delete attributes that are not allowed for users 
                delete Message["trigger"];
                delete Message["error"];
                delete Message["log"];
                delete Message["timestamp"];
                delete Message["type"];
                delete Message["logschema_id"];
    
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

function fetch_log(from_id=null, to_id=null) {
    var params = {
        "from_id": from_id,
        "to_id": to_id
    };
    
    $.post('/fetch_execution_log', params,
        function(res) {
            // success
            if (res.status) {
                // Update execution log
                msg_log = JSON.parse(res['imap_log']);
                
                // append new logs from the server
                var new_msg_key = $(Object.keys(msg_log)).not(Object.keys(log_backup)).get();      
                console.log(new_msg_key);                  
                append_log(new_msg_key.reduce((a, c) => ({ ...a, [c]: msg_log[c] }), {}), false);
                
                // update min and max of log IDs
                if (res["log_min_id"] != -1)   
                    log_min_id = (!log_min_id || res["log_min_id"] < log_min_id) ? res["log_min_id"] : log_min_id;
                if (res["log_max_id"] != -1)   
                    log_max_id = (!log_max_id || res["log_max_id"] > log_max_id) ? res["log_max_id"] : log_max_id;
                    
                log_backup = msg_log;
            }
            else {
                notify(res, false);

                if('imap_authenticated' in res && !res['imap_authenticated']) {
                    alert(res["code"]);
                    window.location.href = "/editor"
                }

            }

            setTimeout(function() {
                fetch_log(log_max_id+1, null);
            }, 2000) // 2 second
        }
    ).fail(function(res) {
        alert("Please refresh the page!");
    });
}

$(document).ready(function() {
    var table = $('#console-table').DataTable( {
        "language": {
            "emptyTable": "There hasn't been no action at YouPS account yet! Turn on your YouPS to get on action!"
        },
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
            { "orderable": false },
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
