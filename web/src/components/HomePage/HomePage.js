import React from "react";
import "./HomePage.css";

const HomePage = (props) => {
  return (
    <div className="home-page-wrapper">
      <div className="home-page-info-wrapper">
        <div className="title">Welcome</div>
        <div className="subtitle">It's still the 2010s...</div>
      </div>

      <div className="home-page-form-wrapper">{props.formElement}</div>
    </div>
  );
};

export default HomePage;
