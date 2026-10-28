const i18n = require("../../utils/i18n");
const workspace = require("../../utils/workspace");
const context = require("../../utils/clientContext");
const u = require("../../utils/workspaceUi");
const { approvedProfileContext } = require("../../utils/profileContext");
const { boundedWindow } = require("../../utils/renderBudget");
const GROUPS = ["before_arrival", "after_arrival", "first_week", "urgent", "optional"];
const EMPTY = {caseId:"", item:null, groups:[], appliedContext:{}, useProfile:false,
  city:"", purpose:"", institution:"", deadline:"", loading:false, saving:false, error:"", offset:0};

const SCENARIOS = [
  { label: "Tourism", key: "tourism", value: "tourism" },
  { label: "Study", key: "study", value: "study" },
  { label: "Work", key: "work", value: "work" },
  { label: "Medical", key: "medical", value: "medical" },
  { label: "Emergency", key: "emergency", value: "emergency" },
  { label: "Payments", key: "payments", value: "payments" },
  { label: "Housing", key: "housing", value: "housing" },
  { label: "Business", key: "business", value: "business" }
];

Page({
  data: Object.assign({}, i18n.pageState(), {
    selectedIndex: 1,
    selectedLabel: SCENARIOS[1].label,
    scenarioLabels: SCENARIOS.map((scenario) => scenario.label),
    loading: false,
    error: "",
    checklist: null,
    warnings: [],
    sourceIds: [],
    escalationRecommended: false,
    ...EMPTY,
    statusKeys: ["todo", "in_progress", "done", "skipped"], statusLabels: []
  }),
  onLoad(options = {}) {
    this._ownerEpoch = context.getOwnerEpoch();
    this._overrides = {};
    this.setData({caseId:options.case_id || "", useProfile:Boolean(options.case_id)});
  },
  currentOwner() {
    if (this._ownerEpoch === context.getOwnerEpoch()) return true;
    this._case = null;
    this._overrides = {};
    u.resetOnOwnerChange(this, {...EMPTY, selectedIndex:1,
      selectedLabel:this.data.scenarioLabels[1] || SCENARIOS[1].label});
    return false;
  },

  onScenarioChange(event) {
    const selectedIndex = Number(event.detail.value);
    if (this.data.loading || !SCENARIOS[selectedIndex]) return;
    this.setData({
      selectedIndex,
      selectedLabel: this.data.scenarioLabels[selectedIndex]
    });
  },

  generateChecklist() {
    if (!this.currentOwner() || this.data.loading || this.data.saving || this.data.caseId) return;
    const scenario = SCENARIOS[this.data.selectedIndex].value;
    const current = u.latestRequest(this, "plan");
    const payload = u.retryableCreate(this, "plan", {
      scenario, language:context.getPreferredLanguage(), use_profile_context:this.data.useProfile,
      overrides:{...this._overrides}
    }, workspace.requestId);
    this.setData({ loading: true, error: "" });
    return workspace.createPlan(payload)
      .then((response) => {
        if (!current()) return;
        u.finishCreate(this, "plan");
        this.showCase(response.case);
      })
      .catch((error) => {
        if (current()) u.error(this, error);
      });
  },
  showCase(item) {
    if (!this.currentOwner() || !item) return;
    this._case = item;
    const savedScenario=u.scenarios().find(value=>value.value===item.scenario);
    const scenarioIndex=SCENARIOS.findIndex(value=>value.value===item.scenario);
    const projection = boundedWindow(item.tasks || [], {offset:this.data.offset, limit:20});
    const tasks = projection.items.map(task => ({
      task_id:task.task_id,group:task.group,status:task.status,priority:task.priority,due_at:task.due_at,
      title:String(task.title || "").slice(0,200), description:String(task.description || "").slice(0,600),
      required_documents:(task.required_documents || []).slice(0,20).map(value=>String(value).slice(0,200)),
      estimated_time:task.estimated_time ? String(task.estimated_time).slice(0,100) : null,
      source_ids:(task.source_ids || []).slice(0,20).map(value=>String(value).slice(0,128)),
      community_source_ids:(task.community_source_ids || []).slice(0,20).map(value=>String(value).slice(0,128)),
      statusIndex:this.data.statusKeys.indexOf(task.status)
    }));
    this.setData({caseId:item.case_id, item:{title:item.title,status:item.status},
      selectedIndex:scenarioIndex>=0 ? scenarioIndex : this.data.selectedIndex,
      selectedLabel:savedScenario ? savedScenario.label : item.scenario,
      loading:false,saving:false,error:"", warnings:item.plan_warnings || [],
      appliedContext:this.data.useProfile ? approvedProfileContext(item.context) : {},
      groups:GROUPS.map(key=>({key,label:this.data.ui[key],items:tasks.filter(t=>(t.group || "optional")===key)})),
      offset:projection.offset,hasPrevious:projection.hasPrevious,hasNext:projection.hasNext});
  },
  load() {
    if (!this.data.caseId || !this.currentOwner()) return Promise.resolve();
    const current=u.latestRequest(this,"plan"), id=this.data.caseId;
    this.setData({loading:true,error:""});
    return workspace.getCase(id).then(result=>{if(current())this.showCase(result.case);})
      .catch(error=>{if(current())u.error(this,error);});
  },
  editField(event) {
    if (!this.currentOwner() || this.data.loading || this.data.saving || this.data.caseId) return;
    const field=event.currentTarget.dataset.field;
    if (!["city","purpose","institution","deadline"].includes(field)) return;
    const value=event.detail.value;
    this._overrides[field]=field==="deadline" ? value || null : value;
    this.setData({[field]:value});
  },
  useProfile(event) {
    if (!this.currentOwner() || this.data.loading || this.data.saving) return;
    const enabled=Boolean(event.detail.value), current=u.latestRequest(this,"profile");
    this.setData({useProfile:enabled,appliedContext:{}});
    if (this.data.caseId) {
      if (enabled && this._case) this.showCase(this._case);
      return;
    }
    if (!enabled) return;
    return workspace.getProfile().then(result=>{
      if(current() && this.data.useProfile && !this.data.caseId)
        this.setData({appliedContext:approvedProfileContext(result.profile)});
    }).catch(error=>{if(current())u.error(this,error);});
  },
  taskStatus(event) {
    if (!this.currentOwner() || this.data.saving || this.data.loading || !this._case || this._case.status!=="open") return;
    const taskId=event.currentTarget.dataset.id, status=this.data.statusKeys[Number(event.detail.value)];
    if (!status || !this._case.tasks.some(t=>t.task_id===taskId)) return;
    const current=u.latestRequest(this,"plan");
    this.setData({saving:true,error:""});
    return workspace.updateTask(this.data.caseId,taskId,{status}).then(result=>{
      if(current())this.showCase(result.case);
    }).catch(error=>{if(current())u.error(this,error);});
  },
  taskAction(event) {
    if (!this.currentOwner() || !this._case) return;
    const task=this._case.tasks.find(t=>t.task_id===event.currentTarget.dataset.id);
    if (!task) return;
    if (task.action==="support") return wx.navigateTo({url:"/pages/support/index"});
    if (task.action==="explain") return wx.navigateTo({url:"/pages/explain/index"});
    getApp().globalData.pendingChatPrefill=task.title;
    wx.navigateTo({url:"/pages/chat/index" + (this.data.useProfile ? "?case_id="+encodeURIComponent(this.data.caseId) : "")});
  },
  openCase() {
    if(this.currentOwner() && this.data.caseId)
      wx.navigateTo({url:"/pages/case-detail/index?id="+encodeURIComponent(this.data.caseId)});
  },
  pageTasks(event) {
    if (!this.currentOwner() || !this._case) return;
    this.setData({offset:Math.max(0,this.data.offset+Number(event.currentTarget.dataset.direction)*20)});
    this.showCase(this._case);
  },
  newPlan() {
    if (!this.currentOwner() || this.data.loading || this.data.saving) return;
    this._case=null; this._overrides={};
    u.invalidateRequests(this);u.finishCreate(this,"plan");
    this.setData({...EMPTY,selectedIndex:1,
      selectedLabel:this.data.scenarioLabels[1] || SCENARIOS[1].label});
  },
  onShow() {
    this.currentOwner();
    i18n.refresh(this);
    const scenarioLabels = SCENARIOS.map((scenario) => this.data.ui[scenario.key] || scenario.label);
    this.setData({ scenarioLabels, selectedLabel: this.data.caseId
      ? this.data.selectedLabel : scenarioLabels[this.data.selectedIndex],
      statusLabels:this.data.statusKeys.map(key=>this.data.ui[key]) });
    if(this.data.caseId && !this.data.saving) return this.load();
  },
  onUnload() {u.invalidateRequests(this);}
});
