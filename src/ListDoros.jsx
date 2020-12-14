import React from "react";
import { withRouter } from "react-router";


const ListDoros = () => {
  return (
    // <div style={{ maxWidth: "800px" }}>
    //   <div className="dropdown ">
    //     <button
    //       className="btn btn-secondary dropdown-toggle"
    //       type="button"
    //       data-toggle="dropdown"
    //       aria-haspopup="true"
    //       aria-expanded="false"
    //     >
    //       لیست دروس
    //       <div className="dropdown-menu">
    //         <p className="dropdown-item">ریاضی</p>
    //         <p className="dropdown-item">شیمی</p>
    //         <p className="dropdown-item">زبان </p>
    //       </div>
    //     </button>

    //     <button className="btn btn-light float-left">اضافه کن</button>
    //   </div>

    //   <div className=" bg-danger   ">
    //     <p> </p>
    //   </div>
    // </div>
<div>
<form className="container list header " >
<select className="float-right btn btn-dark btn-lg btn-group-toggle">
  <option>ریاضی</option>
  <option>شیمی</option>
  <option>زبان</option>
  <option>ویزه</option>
</select>

<h1 className="text-center  text-dark  "> دروس
<button className="btn btn-dark btn-lg   float-left "> ثبت </button>
</h1>
</form>

<div className="foot">


</div>


</div>
  );
};

export default withRouter(ListDoros);
