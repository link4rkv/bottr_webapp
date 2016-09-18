	WEB_SOCKET_SWF_LOCATION = "WebSocketMain.swf";
	ws_init('ws://localhost:8888/ws_channel');

	function writeMsgToTextArea(msg){
		document.getElementById('text_area').value = msg;
	}


	function ws_init(url) {
		ws = new WebSocket(url);
		ws.onopen = function(){	
			console.log("Connection established");
		};
		ws.onmessage = function(msg){
			console.log(msg);
			console.log(msg.data);
			console.log("Message Received:  '" + msg.data + "'" );
			writeMsgToTextArea(msg.data);
		};
		ws.onclose = function(){
			console.log("Connection Closed");
		}
	}

	function ws_send(msg){
		console.log("Sending: " + msg);
		writeMsgToTextArea(msg);
		ws.send(msg);
	}