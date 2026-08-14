
import Api from "./api"

export const generateApi  = new Api({
  url: "/generate" 
})

export const calibrationApi = new Api({url:"/calibration"})

export const roiOptimizeApi = new Api({url:"/roi_optimize"})

export const paramSensitivityApi = new Api({url:"/param_sensitivity"})

export const cleanApi = new Api({url:"/clean"})

export const aiChatApi = new Api({url:"/ai/chat"})

export const aiStatusApi = new Api({url:"/ai/status"})
