var watched_message = [];
function fetch_watch_message(container="body") {
  var params = {
      "watched_message": watched_message
  };
  
  $.post('/fetch_watch_message', params,
      function(res) {
        console.log(res);
        console.log(res["message_row"]);

          if (res.status) {
              if ( !res['watch_status'] ) {
                  spin_watch_btn(false);
                  return;
              }

              if(res["log"]) { // something went wrong
                  watching_msg_container.find("span").text("");
                  watching_msg_container.find("[name='subject']").text( res["log"] );
              }
              // TODO if the message is from a different folder, noop 
              // uid: message schema id
              else  { // If everything successful
                  $.each(res['message_rows'], function(i, message) {
                    if( watched_message.indexOf( res['contexts'][i]['base_message_id'] ) == -1 ) {
                      $(container+ " .message-parameter-table").prepend( message );
                      
                      watched_message.push( res['contexts'][i]['base_message_id'] );
                    }
                  })
              }
              
              // show_loader(false);
          }
          else if (!res['uid']) {
              
          }
          else {
              notify(res, false);
          }

          setTimeout(fetch_watch_message, 1 * 1000); // 1 second
      }
  ).fail(function(res) {
      alert("Please refresh the page!");
  });
}