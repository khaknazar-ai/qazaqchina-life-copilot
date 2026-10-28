const i18n=require("../../utils/i18n");
Page({
 data:Object.assign({}, i18n.pageState(), {phrase:"我需要帮助。请帮我联系紧急救援。",showPhrase:false,contacts:[],contactStatus:"not_configured"}),
 onShow(){i18n.refresh(this);},
 showPhrase(){this.setData({showPhrase:true});},
 closePhrase(){this.setData({showPhrase:false});},
 copyPhrase(){wx.setClipboardData({data:this.data.phrase});},
 goSupport(){
  getApp().globalData.supportDraftContext={source:"emergency",scenario:"emergency",risk_level:"emergency",
   escalation_reason:"emergency",urgency:"urgent",not_emergency_dispatch:true,safety_warning:this.data.ui.emergencyNotice};
  wx.navigateTo({url:"/pages/support/index"});
 },
 goChat(){getApp().globalData.pendingChatPrefill=this.data.ui.samplePassportMessage;wx.navigateTo({url:"/pages/chat/index"});}
});
