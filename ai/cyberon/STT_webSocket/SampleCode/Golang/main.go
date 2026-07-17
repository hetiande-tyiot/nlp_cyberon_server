package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"path"
	"sync"

	"github.com/gorilla/websocket"
)

var token = "None"
var url string
var file string
var domain string
var audioType string

func main() {
	//read params
	if len(os.Args) < 2 {
		log.Println(os.Args[0], " [wav file] [ws url] [domain] [rate]")
		return
	}
	file = os.Args[1]
	if _, err := os.Stat(file); os.IsNotExist(err) {
		log.Println("file not found")
		return
	}
	url = "ws://[entry point]/SttProxy/recognition"
	if len(os.Args) > 2 {
		url = os.Args[2]
	}
	domain = "freeSTT-zh-TW"
	if len(os.Args) > 3 {
		domain = os.Args[3]
	}
	rate := "16000"
	if len(os.Args) > 4 {
		rate = os.Args[4]
	}
	switch path.Ext(file) {
	case ".pcm":
		audioType = "audio/L16; rate=" + rate
	case ".spx":
		audioType = "audio/speex; rate=16000"
	case ".wav":
		audioType = "audio/wav"
	default:
		log.Println("file type not suppout")
		return
	}

	// connect websocket server
	c, _, err := websocket.DefaultDialer.Dial(url, nil)
	if err != nil {
		log.Fatal(err)
		return
	}
	defer c.Close()

	wg := sync.WaitGroup{}
	wg.Add(1)
	//recv server response thread
	go func() {
		defer wg.Done()
		stateCount := 0
		for {
			var result map[string]interface{}
			err := c.ReadJSON(&result)
			if err != nil {
				log.Println("read:", err)
				return
			}

			// check error code
			if v, ok := result["err_code"]; ok {
				errCode := v.(float64)
				if errCode != 0 {
					log.Println("error code: ", v)
					if v, ok := result["err_msg"]; ok {
						log.Println("error msg: ", v)
					}
					return
				}
			}

			// read server response state is listening or result
			if v, ok := result["state"]; ok {
				if v.(string) == "listening" {
					stateCount++
					// read server second state listening do close connection
					if stateCount >= 2 {
						return
					} else if stateCount == 1 {
						// first read listening
						txt := `{"token":"` + token + `","action":"start","domain":"` + domain + `","platform":"web","uid":"Golang-Tester","type":"` + audioType + `"}`
						o := map[string]interface{}{}
						err := json.Unmarshal([]byte(txt), &o)
						if err != nil {
							fmt.Println(err)
							return
						}
						// send start action to server
						err = c.WriteJSON(o)
						if err != nil {
							log.Println(err)
							return
						}
						go func() {
							// read file data
							data, err := ioutil.ReadFile(file)
							if err != nil {
								fmt.Println(err)
								return
							}
							// send data to server
							err = c.WriteMessage(websocket.BinaryMessage, data)
							if err != nil {
								fmt.Println(err)
								return
							}
							// send stop to server
							err = c.WriteJSON(map[string]interface{}{"action": "stop"})
							if err != nil {
								fmt.Println(err)
								return
							}
						}()
					}
				} else {
					// read state is result
					if v, ok := result["recog_result"]; ok {
						fmt.Println(v)
					}
				}
			}
		}
	}()
	wg.Wait()
	cm := websocket.FormatCloseMessage(websocket.CloseNormalClosure, "Connection closed.")
	if err := c.WriteMessage(websocket.CloseMessage, cm); err != nil {
		log.Println(err)
	}
}
