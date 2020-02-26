function notify(res, on_success){
	if(!res.status){
		noty({text: "Error: " + res.code, dismissQueue: true, timeout:2000, force: true, type: 'error', layout: 'topRight'});
	}else{
		if(on_success){
			var msg = "Success! ";
			var timeout = 2000;
			if ("code" in res) {
				msg = res["code"]
				timeout = 4000;
			}
				
			noty({text: msg, dismissQueue: true, timeout:timeout, force: true, type:'success', layout: 'topRight'});
		}
	}
}