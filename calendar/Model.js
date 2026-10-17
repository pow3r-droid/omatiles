// Month grid (Monday first, 6 weeks) and the events that touch a day.
function grid(year, month) {
    var offset=(new Date(year,month,1).getDay()+6)%7, count=new Date(year,month+1,0).getDate();
    return Array.from({length:42},function(_,i){return i>=offset && i<offset+count ? i-offset+1 : 0;});
}
function dayEvents(events,year,month,day) {
    var start=new Date(year,month,day).getTime(), end=new Date(year,month,day+1).getTime();
    return events.filter(function(e){var finish=e.end>e.time ? e.end : e.time+1; return e.time<end && finish>start;});
}
function onDay(events,year,month,day) {return dayEvents(events,year,month,day).length>0;}
if(typeof module!=='undefined') module.exports={grid:grid,dayEvents:dayEvents,onDay:onDay};
